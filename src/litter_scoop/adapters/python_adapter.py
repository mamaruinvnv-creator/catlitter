"""Python redundancy detector, built on the standard-library ``ast`` module.

Rules implemented:

============================== ============================================
rule id                        what it catches
============================== ============================================
unused-import                  imported names never referenced in-file
unused-toplevel-symbol         module-level function/class never referenced
unused-local                   local variable assigned but never read
unreachable-code               statements after return/raise/break/continue
duplicate-definition           same name defined twice in one scope
empty-stub                     function body reduced to ``pass`` / ``...``
commented-code                 runs of commented-out source lines
============================== ============================================

The detector is deliberately conservative: dynamic constructs (``import *``,
``__all__`` re-exports, decorated functions, dunder names, ``if __name__ ==
"__main__"`` blocks, test files) are exempted to keep the false-positive rate
low.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ..models import Severity
from .base import BaseAdapter

# A commented line that looks like source code rather than prose.
_CODE_COMMENT_RE = re.compile(
    r"^\s*#\s*("
    r"from\s+[\w.]+\s+import\s"
    r"|import\s+\w"
    r"|def\s+\w+\s*\("
    r"|async\s+def\s+\w+\s*\("
    r"|class\s+\w+"
    r"|return\b"
    r"|raise\s+\w"
    r"|if\s+.*:\s*$"
    r"|elif\s+.*:\s*$"
    r"|else:\s*$"
    r"|for\s+.*:\s*$"
    r"|while\s+.*:\s*$"
    r"|try:\s*$"
    r"|except\b.*:\s*$"
    r"|finally:\s*$"
    r"|with\s+.*:\s*$"
    r"|@[\w.]+"
    r"|print\s*\("
    r"|self\.\w+\s*="
    r"|cls\.\w+\s*="
    r"|[A-Za-z_]\w*(\.[A-Za-z_]\w*)*\s*=\s*[^=]"
    r"|[A-Za-z_]\w*\([^)]*\)\s*$"
    r"|\)"
    r"|\]"
    r"|}"
    r")"
)

_TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


class _NameLoader(ast.NodeVisitor):
    """Collect every name that is *read* anywhere in a subtree."""

    def __init__(self) -> None:
        self.loaded: dict[str, int] = {}

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if isinstance(node.ctx, ast.Load):
            self.loaded[node.id] = self.loaded.get(node.id, 0) + 1
        self.generic_visit(node)


def _all_exports(tree: ast.Module) -> set[str]:
    exports: set[str] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    exports.add(elt.value)
    return exports


def _is_main_guard(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and any(
            isinstance(c, ast.Constant) and c.value == "__main__"
            for c in node.test.comparators
        )
    )


class PythonAdapter(BaseAdapter):
    name = "python"
    extensions = (".py", ".pyi")

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def analyze(self, path: Path, rel_path: str, source: str) -> list:
        findings = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings  # let other tools handle broken files

        lines = source.splitlines()
        loader = _NameLoader()
        loader.visit(tree)
        loaded = loader.loaded
        exports = _all_exports(tree)
        future_annotations = any(
            isinstance(n, ast.ImportFrom)
            and n.module == "__future__"
            and any(a.name == "annotations" for a in n.names)
            for n in tree.body
        )

        findings.extend(self._unused_imports(tree, lines, loaded, exports, future_annotations, rel_path))
        findings.extend(
            self._unused_toplevel(tree, lines, loaded, exports, rel_path)
        )
        findings.extend(self._unused_locals(tree, rel_path))
        findings.extend(self._unreachable(tree, lines, rel_path))
        findings.extend(self._duplicate_definitions(tree, lines, rel_path))
        findings.extend(self._empty_stubs(tree, lines, rel_path))
        if self.context.config.detect_commented_code:
            findings.extend(self._commented_code(lines, rel_path))

        return [f for f in findings if self.context.config.rule_enabled(f.rule_id)]

    # ------------------------------------------------------------------
    def _snippet(self, lines: list[str], start: int, end: int, cap: int = 6) -> str:
        chunk = lines[start - 1 : end]
        if len(chunk) > cap:
            chunk = chunk[:cap] + ["…"]
        return "\n".join(chunk)

    def _unused_imports(self, tree, lines, loaded, exports, future_annotations, rel_path):
        findings = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.split(".")[0]
                    if bound == "*" or bound in exports:
                        continue
                    if loaded.get(bound, 0) == 0:
                        sev = Severity.LOW if future_annotations else Severity.MEDIUM
                        findings.append(
                            self.make_finding(
                                "unused-import", rel_path, "python",
                                f"导入的 “{bound}” 在本文件中从未被使用",
                                node.lineno, node.end_lineno or node.lineno,
                                symbol=bound, severity=sev,
                                confidence=0.85 if not future_annotations else 0.6,
                                snippet=self._snippet(lines, node.lineno, node.end_lineno or node.lineno),
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                # ``from __future__ import ...`` is a compiler directive,
                # never an unused value.
                if node.module == "__future__":
                    continue
                # Skip star imports; TYPE_CHECKING-guarded re-export blocks
                # are still reported (low risk, easy to restore from the bag).
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound = alias.asname or alias.name
                    if bound in exports:
                        continue
                    if loaded.get(bound, 0) == 0:
                        sev = Severity.LOW if future_annotations else Severity.MEDIUM
                        findings.append(
                            self.make_finding(
                                "unused-import", rel_path, "python",
                                f"从 “{node.module or ''}” 导入的 “{bound}” 从未被使用",
                                node.lineno, node.end_lineno or node.lineno,
                                symbol=bound, severity=sev,
                                confidence=0.85 if not future_annotations else 0.6,
                                snippet=self._snippet(lines, node.lineno, node.end_lineno or node.lineno),
                            )
                        )
        return findings

    def _unused_toplevel(self, tree, lines, loaded, exports, rel_path):
        findings = []
        if self.context.is_test_file(rel_path):
            return findings
        main_guard_lines: set[int] = set()
        for node in tree.body:
            if _is_main_guard(node):
                for sub in ast.walk(node):
                    main_guard_lines.add(getattr(sub, "lineno", -1))

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            name = node.name
            if name.startswith("__") and name.endswith("__"):
                continue
            if name in exports:
                continue
            if node.decorator_list:  # decorated => registry/side-effect API
                continue
            if node.lineno in main_guard_lines:
                continue
            # Used inside this same file (definition itself is a Store, not Load).
            if loaded.get(name, 0) > 0:
                continue
            # Referenced from other files in the project?
            if self.context.global_name_refs.get(name, 0) > 0:
                continue
            kind = "类" if isinstance(node, ast.ClassDef) else "函数"
            findings.append(
                self.make_finding(
                    "unused-toplevel-symbol", rel_path, "python",
                    f"顶层{kind} “{name}” 在整个项目中都没有被引用",
                    node.lineno, node.end_lineno or node.lineno,
                    symbol=name, severity=Severity.MEDIUM, confidence=0.7,
                    snippet=self._snippet(lines, node.lineno,
                                          min(node.lineno + 2, node.end_lineno or node.lineno)),
                )
            )
        return findings

    def _unused_locals(self, tree, rel_path) -> list:
        findings = []

        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            # Names used anywhere inside the function (incl. nested scopes).
            inner_loader = _NameLoader()
            for stmt in fn.body:
                inner_loader.visit(stmt)
            inner_used = inner_loader.loaded

            arg_names = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
            if fn.args.vararg:
                arg_names.add(fn.args.vararg.arg)
            if fn.args.kwarg:
                arg_names.add(fn.args.kwarg.arg)

            declared_global: set[str] = set()
            for stmt in ast.walk(fn):
                if isinstance(stmt, (ast.Global, ast.Nonlocal)):
                    declared_global.update(stmt.names)

            for stmt in ast.walk(fn):
                if not isinstance(stmt, ast.Assign):
                    continue
                if len(stmt.targets) != 1:
                    continue
                target = stmt.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name == "_" or name.startswith("_"):
                    continue
                if name in arg_names or name in declared_global:
                    continue
                # Upper-case module-style constants inside a function are rare;
                # still flag only when zero reads.
                if inner_used.get(name, 0) == 0:
                    findings.append(
                        self.make_finding(
                            "unused-local", rel_path, "python",
                            f"局部变量 “{name}” 赋值后从未被读取",
                            stmt.lineno, stmt.end_lineno or stmt.lineno,
                            symbol=name, severity=Severity.MEDIUM, confidence=0.75,
                        )
                    )
        return findings

    def _unreachable(self, tree, lines, rel_path) -> list:
        findings = []
        seen: set[tuple[str, int]] = set()

        def scan_body(body: list[ast.stmt]) -> None:
            # 1) flag statements after a terminator in this same block
            for idx, stmt in enumerate(body):
                if isinstance(stmt, _TERMINATORS) and idx + 1 < len(body):
                    dead = body[idx + 1]
                    last = body[-1]
                    key = (rel_path, dead.lineno)
                    if key not in seen:
                        seen.add(key)
                        findings.append(
                            self.make_finding(
                                "unreachable-code", rel_path, "python",
                                "该语句位于 return/raise/break/continue 之后，永远不会执行",
                                dead.lineno, last.end_lineno or last.lineno,
                                severity=Severity.HIGH, confidence=0.95,
                                snippet=self._snippet(lines, dead.lineno,
                                                      min(dead.lineno + 3, last.end_lineno or dead.lineno)),
                            )
                        )
                    break
            # 2) recurse into every nested statement block (function bodies,
            #    if/for/with/try branches, etc.)
            for stmt in body:
                for _, value in ast.iter_fields(stmt):
                    if isinstance(value, list):
                        nested = [v for v in value if isinstance(v, ast.stmt)]
                        if nested:
                            scan_body(nested)
                    elif isinstance(value, ast.stmt):
                        scan_body([value])

        scan_body(tree.body)
        return findings

    def _duplicate_definitions(self, tree, lines, rel_path) -> list:
        findings = []
        seen: dict[str, ast.AST] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in seen:
                    findings.append(
                        self.make_finding(
                            "duplicate-definition", rel_path, "python",
                            f"“{node.name}” 在模块顶层被重复定义，前一个定义会被覆盖",
                            node.lineno, node.end_lineno or node.lineno,
                            symbol=node.name, severity=Severity.HIGH, confidence=0.9,
                            snippet=self._snippet(lines, node.lineno, node.lineno),
                        )
                    )
                else:
                    seen[node.name] = node
        return findings

    def _empty_stubs(self, tree, lines, rel_path) -> list:
        findings = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = node.body
            # docstring + pass/... => empty stub
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            ) and isinstance(body[0].value.value, str):
                body = body[1:]
            if len(body) == 1 and isinstance(
                body[0], (ast.Pass, ast.Expr)
            ) and (
                isinstance(body[0], ast.Pass)
                or (isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and body[0].value.value is Ellipsis)
            ):
                findings.append(
                    self.make_finding(
                        "empty-stub", rel_path, "python",
                        f"“{node.name}” 是空壳函数（只有 docstring 与 pass/…）",
                        node.lineno, node.end_lineno or node.lineno,
                        symbol=node.name, severity=Severity.LOW, confidence=0.55,
                        snippet=self._snippet(lines, node.lineno, node.end_lineno or node.lineno),
                    )
                )
        return findings

    def _commented_code(self, lines: list[str], rel_path: str) -> list:
        findings = []
        run_start: int | None = None
        run_len = 0
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            is_code_comment = bool(_CODE_COMMENT_RE.match(line))
            # Ignore shebang / encoding declarations / section dividers.
            if stripped.startswith("#!") or stripped.startswith("# -*-"):
                is_code_comment = False
            if is_code_comment:
                if run_start is None:
                    run_start = idx
                run_len += 1
            else:
                if run_start is not None and run_len >= 3:
                    end = idx - 1
                    findings.append(
                        self.make_finding(
                            "commented-code", rel_path, "python",
                            f"连续 {run_len} 行被注释掉的代码，疑似废弃代码块",
                            run_start, end, severity=Severity.LOW, confidence=0.6,
                            snippet=self._snippet(lines, run_start, end),
                        )
                    )
                run_start, run_len = None, 0
        if run_start is not None and run_len >= 3:
            findings.append(
                self.make_finding(
                    "commented-code", rel_path, "python",
                    f"连续 {run_len} 行被注释掉的代码，疑似废弃代码块",
                    run_start, len(lines), severity=Severity.LOW, confidence=0.6,
                    snippet=self._snippet(lines, run_start, len(lines)),
                )
            )
        return findings
