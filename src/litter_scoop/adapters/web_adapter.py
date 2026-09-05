"""JavaScript / TypeScript redundancy detector (lexer-level, dependency-free).

A full JS/TS AST would need node_modules; instead this adapter builds a
character mask that blanks out strings, template literals and comments, then
runs conservative regex rules on real code regions:

* unused-import             - ESM / CommonJS imports never referenced
* unused-debug-statement    - leftover ``console.log`` / ``debugger``
* unused-top-level-function - non-exported function declared but never called
* commented-code            - commented-out source blocks
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Severity
from .base import BaseAdapter

_IMPORT_RE = re.compile(
    r"""^\s*
        import\s+
          (?:
            (?P<default>[A-Za-z_$][\w$]*) |
            \*\s+as\s+(?P<ns>[A-Za-z_$][\w$]*) |
            \{(?P<named>[^}]*)\}
          )
          (?:\s*,\s*\{(?P<named2>[^}]*)\})?
        \s+from\s*['"][^'"]+['"]
    """,
    re.VERBOSE,
)
_BARE_IMPORT_RE = re.compile(r"""^\s*import\s*['"][^'"]+['"]""")
_REQUIRE_RE = re.compile(
    r"""^(?:const|let|var)\s+
        (?P<name>[A-Za-z_$][\w$]*)
        \s*=\s*require\(\s*['"][^'"]+['"]\s*\)""",
    re.VERBOSE,
)
_FN_DECL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
)
_EXPORT_FN_RE = re.compile(r"^export\s+(?:async\s+)?function\s+")
_DEBUG_RE = re.compile(r"\bconsole\.(log|debug|info|warn|error)\s*\(|\bdebugger\b")

_LINE_COMMENT_CODE_RE = re.compile(
    r"^\s*//\s*("
    r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*="
    r"|function\s+[A-Za-z_$]"
    r"|import\s+"
    r"|export\s+"
    r"|return\s+"
    r"|if\s*\(.*\)\s*\{"
    r"|for\s*\(.*\)\s*\{"
    r"|while\s*\(.*\)\s*\{"
    r"|[A-Za-z_$][\w$.]*\s*=\s*[^=]"
    r"|[A-Za-z_$][\w$.]*\([^)]*\)\s*;?\s*$"
    r"|\}[\]);,]*\s*$"
    r"|\)"
    r")"
)


def build_code_mask(source: str) -> list[bool]:
    """Return a per-character mask: True where the char is real code."""
    mask = [True] * len(source)
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if ch in ("'", '"', "`"):
            quote = ch
            mask[i] = False
            i += 1
            while i < n:
                mask[i] = False
                if source[i] == "\\":
                    if i + 1 < n:
                        mask[i + 1] = False
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < n and source[i] != "\n":
                mask[i] = False
                i += 1
            continue
        if ch == "/" and nxt == "*":
            mask[i] = mask[i + 1] = False
            i += 2
            while i < n and not (source[i] == "*" and i + 1 < n and source[i + 1] == "/"):
                mask[i] = False
                i += 1
            if i < n:
                mask[i] = mask[i + 1] = False
                i += 2
            continue
        i += 1
    return mask


def blank_non_code(source: str, mask: list[bool]) -> str:
    return "".join(ch if ok else ("\n" if ch == "\n" else " ")
                   for ch, ok in zip(source, mask))


class WebAdapter(BaseAdapter):
    name = "web"
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte")

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def analyze(self, path: Path, rel_path: str, source: str) -> list:
        findings = []
        mask = build_code_mask(source)
        code_only = blank_non_code(source, mask)
        lines = source.splitlines()
        code_lines = code_only.splitlines()

        imports = self._collect_imports(lines, code_lines)
        findings.extend(self._unused_imports(imports, code_only, lines, rel_path))
        findings.extend(self._debug_statements(code_lines, lines, rel_path))
        findings.extend(self._unused_functions(code_only, lines, rel_path))
        if self.context.config.detect_commented_code:
            findings.extend(self._commented_lines(lines, rel_path))
            findings.extend(self._commented_blocks(source, mask, rel_path))

        return [f for f in findings if self.context.config.rule_enabled(f.rule_id)]

    # ------------------------------------------------------------------
    @staticmethod
    def _collect_imports(raw_lines: list[str], code_lines: list[str]) -> list[tuple[int, str]]:
        names: list[tuple[int, str]] = []
        for idx, line in enumerate(raw_lines, start=1):
            # The module specifier is a string and therefore blanked in the
            # masked view, so parse the raw line but confirm the keyword lives
            # in real code (not inside a comment) via the masked line.
            code_line = code_lines[idx - 1] if idx - 1 < len(code_lines) else line
            in_code_region = code_line.lstrip().startswith(("import", "const", "let", "var"))
            if not in_code_region:
                continue
            if _BARE_IMPORT_RE.match(line):
                continue
            m = _IMPORT_RE.match(line)
            if m:
                if m.group("default"):
                    names.append((idx, m.group("default")))
                if m.group("ns"):
                    names.append((idx, m.group("ns")))
                for group_name in ("named", "named2"):
                    group = m.group(group_name)
                    if group:
                        for part in group.split(","):
                            part = part.strip()
                            if not part:
                                continue
                            alias = part.split(" as ")[-1].strip()
                            if alias:
                                names.append((idx, alias))
                continue
            m = _REQUIRE_RE.match(line)
            if m:
                names.append((idx, m.group("name")))
        return names

    def _unused_imports(self, imports, code_only, lines, rel_path) -> list:
        findings = []
        for line_no, name in imports:
            count = len(re.findall(rf"(?<![\w$.]){re.escape(name)}\b", code_only))
            # The import statement itself mentions the name once.
            if count <= 1:
                findings.append(
                    self.make_finding(
                        "unused-import", rel_path, "javascript",
                        f"导入的 “{name}” 在本文件中从未被使用",
                        line_no, symbol=name, severity=Severity.MEDIUM,
                        confidence=0.8, snippet=lines[line_no - 1].strip(),
                    )
                )
        return findings

    def _debug_statements(self, code_lines, lines, rel_path) -> list:
        findings = []
        for idx, code_line in enumerate(code_lines, start=1):
            if _DEBUG_RE.search(code_line):
                findings.append(
                    self.make_finding(
                        "unused-debug-statement", rel_path, "javascript",
                        "遗留的调试语句（console.*/debugger）",
                        idx, severity=Severity.LOW, confidence=0.9,
                        snippet=lines[idx - 1].strip(),
                    )
                )
        return findings

    def _unused_functions(self, code_only, lines, rel_path) -> list:
        findings = []
        if self.context.is_test_file(rel_path):
            return findings
        for idx, line in enumerate(lines, start=1):
            if _EXPORT_FN_RE.match(line):
                continue
            m = _FN_DECL_RE.match(line)
            if not m:
                continue
            name = m.group(1)
            count = len(re.findall(rf"\b{re.escape(name)}\b", code_only))
            if count <= 1:
                findings.append(
                    self.make_finding(
                        "unused-top-level-function", rel_path, "javascript",
                        f"函数 “{name}” 声明后从未在本文件中被调用，且未导出",
                        idx, symbol=name, severity=Severity.LOW, confidence=0.55,
                        snippet=line.strip(),
                    )
                )
        return findings

    def _commented_lines(self, lines: list[str], rel_path: str) -> list:
        findings = []
        run_start, run_len = None, 0
        for idx, line in enumerate(lines, start=1):
            hit = bool(_LINE_COMMENT_CODE_RE.match(line))
            if hit:
                run_start = run_start or idx
                run_len += 1
            else:
                if run_start is not None and run_len >= 3:
                    findings.append(self._commented_finding(rel_path, run_start, idx - 1, run_len, lines))
                run_start, run_len = None, 0
        if run_start is not None and run_len >= 3:
            findings.append(self._commented_finding(rel_path, run_start, len(lines), run_len, lines))
        return findings

    def _commented_blocks(self, source: str, mask: list[bool], rel_path: str) -> list:
        findings = []
        for m in re.finditer(r"/\*.*?\*/", source, flags=re.DOTALL):
            block = m.group(0)
            block_lines = block.splitlines()
            if len(block_lines) < 3:
                continue
            code_like = sum(
                1 for ln in block_lines
                if re.search(r"[;{}()=]\s*$|^\s*\*?\s*(const|let|var|return|if|for|function)\b", ln)
            )
            if code_like / max(len(block_lines), 1) >= 0.6:
                start_line = source.count("\n", 0, m.start()) + 1
                end_line = source.count("\n", 0, m.end()) + 1
                findings.append(
                    self.make_finding(
                        "commented-code", rel_path, "javascript",
                        "块注释中包含大段疑似被注释掉的代码",
                        start_line, end_line, severity=Severity.LOW,
                        confidence=0.55, snippet="\n".join(block_lines[:6]),
                    )
                )
        return findings

    def _commented_finding(self, rel_path, start, end, length, lines):
        return self.make_finding(
            "commented-code", rel_path, "javascript",
            f"连续 {length} 行被注释掉的代码，疑似废弃代码块",
            start, end, severity=Severity.LOW, confidence=0.55,
            snippet="\n".join(lines[start - 1 : min(end, start + 5)]),
        )
