"""Scan engine: profile the project, index names, run adapters, merge results."""

from __future__ import annotations

import ast
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import REGISTRY, AnalysisContext
from .adapters.python_adapter import _NameLoader
from .config import Config
from .ignore import IgnoreMatcher
from .models import Finding, ProjectProfile, Severity
from .project import EXTENSION_LANGUAGE, profile_project

_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


@dataclass(slots=True)
class ScanResult:
    profile: ProjectProfile
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    skipped_binary: int = 0
    errors: list[str] = field(default_factory=list)

    def by_rule(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.rule_id, []).append(finding)
        return grouped

    def filter_min_severity(self, level: str) -> list[Finding]:
        floor = Severity(level).rank
        return [f for f in self.findings if f.severity.rank >= floor]


def _match_any(rel_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_posix, p) or fnmatch.fnmatch(Path(rel_posix).name, p)
               for p in patterns)


def scan_project(root: Path, config: Config | None = None,
                 extra_ignore: list[str] | None = None) -> ScanResult:
    root = root.resolve()
    config = config or Config.load(root)
    matcher = IgnoreMatcher.load(root, extra_ignore or config.exclude)

    files, profile = profile_project(root, matcher, config.disable_adapters)

    relpaths = {p: p.relative_to(root).as_posix() for p in files}

    # Include / exclude globs from config.
    def kept(path: Path) -> bool:
        rel = relpaths[path]
        if config.exclude and _match_any(rel, config.exclude):
            return False
        if config.include and not _match_any(rel, config.include):
            return False
        return True

    files = [p for p in files if kept(p)]
    relpaths = {p: p.relative_to(root).as_posix() for p in files}

    context = AnalysisContext(
        root=root, files=files, relpaths=relpaths, config=config,
    )
    context.global_name_refs = _build_global_name_index(files, relpaths)

    adapters = [REGISTRY[name](context) for name in profile.adapters if name in REGISTRY]

    findings: list[Finding] = []
    seen: set[tuple] = set()
    scanned = 0
    skipped_binary = 0
    errors: list[str] = []

    for path in files:
        rel = relpaths[path]
        try:
            size = path.stat().st_size
            if size > config.max_file_bytes:
                errors.append(f"跳过超大文件 {rel}（{size} 字节）")
                continue
            raw = path.read_bytes()
            if b"\x00" in raw:
                skipped_binary += 1
                continue
            source = raw.decode("utf-8", errors="replace").lstrip("﻿")
        except OSError as exc:
            errors.append(f"读取失败 {rel}: {exc}")
            continue
        scanned += 1
        for adapter in adapters:
            if not adapter.supports(path):
                continue
            try:
                for finding in adapter.analyze(path, rel, source):
                    key = (finding.path, finding.rule_id, finding.start_line,
                           finding.symbol, finding.end_line)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(finding)
            except Exception as exc:  # an adapter must never kill the scan
                errors.append(f"{adapter.name} 分析 {rel} 失败: {exc}")

    findings.sort(key=lambda f: (f.path, f.start_line, f.rule_id))
    return ScanResult(
        profile=profile,
        findings=findings,
        files_scanned=scanned,
        skipped_binary=skipped_binary,
        errors=errors,
    )


def _build_global_name_index(files: list[Path], relpaths: dict[Path, str]) -> dict[str, int]:
    """Count how often each name is *read* across the whole Python project."""
    index: dict[str, int] = {}
    for path in files:
        ext = path.suffix.lower()
        lang = EXTENSION_LANGUAGE.get(ext, ("", ""))[0]
        try:
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            source = raw.decode("utf-8", errors="replace").lstrip("﻿")
        except OSError:
            continue
        if lang == "python":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            loader = _NameLoader()
            loader.visit(tree)
            for name, count in loader.loaded.items():
                index[name] = index.get(name, 0) + count
            # A name imported/re-exported by another module is "referenced"
            # (ImportFrom aliases are not ast.Name nodes, so add them here).
            for stmt in tree.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module != "__future__":
                    for alias in stmt.names:
                        if alias.name == "*":
                            continue
                        bound = alias.asname or alias.name
                        index[bound] = index.get(bound, 0) + 1
                elif isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        bound = alias.asname or alias.name.split(".")[0]
                        index[bound] = index.get(bound, 0) + 1
        elif lang in ("javascript", "typescript", "vue", "svelte"):
            for name in set(_IDENT_RE.findall(source)):
                index.setdefault(name, 0)  # presence known, counts stay file-local
    return index
