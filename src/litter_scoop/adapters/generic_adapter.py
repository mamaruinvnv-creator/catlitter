"""Language-agnostic redundancy detector.

These checks work for every text file regardless of language:

* empty-file        - zero bytes / whitespace only
* duplicate-file    - byte-identical copy of another file (keep one, bag rest)
* backup-file       - editor/VCS leftovers (*.bak, *.orig, *~, *.old ...)
* commented-code    - commented-out code for // and -- comment languages
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from ..models import Severity, sha256_bytes
from .base import BaseAdapter

BACKUP_PATTERNS = ("*.bak", "*.orig", "*.old", "*~", "*.swp", "*.swo", "*.tmp", "*.rej")

_SLASH_LANGS = {
    ".go", ".java", ".kt", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".rs", ".php", ".swift", ".scala", ".dart",
}
_DASH_LANGS = {".sql"}
_HASH_LANGS = {".rb", ".sh", ".bash", ".r", ".pl", ".yaml", ".yml", ".toml", ".cfg", ".ini"}

_SLASH_CODE_RE = re.compile(
    r"^\s*//\s*("
    r"(?:const|var|final|let|public|private|static)\s"
    r"|return\s+"
    r"|(?:func|function|def|class|struct|impl|fn)\s+\w"
    r"|import\s+"
    r"|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*=\s*[^=]"
    r"|[A-Za-z_]\w*\([^)]*\)\s*;?\s*$"
    r"|[\}\]\)]+[;,]?\s*$"
    r")"
)
_HASH_CODE_RE = re.compile(
    r"^\s*#\s*("
    r"(?:def|class)\s+\w|require\s+|import\s+|return\s+|"
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*=\s*[^=]|"
    r"[A-Za-z_]\w*\([^)]*\)\s*$|[\}\]\)]+[;,]?\s*$"
    r")"
)


class GenericAdapter(BaseAdapter):
    name = "generic"
    extensions = tuple()  # claims everything; engine always invokes it on text

    def __init__(self, context) -> None:
        super().__init__(context)
        self._hash_owner: dict[str, str] = {}

    def supports(self, path: Path) -> bool:
        return True

    def analyze(self, path: Path, rel_path: str, source: str) -> list:
        findings = []
        findings.extend(self._empty_file(rel_path, source))
        findings.extend(self._backup_file(path, rel_path, source))
        findings.extend(self._duplicate_file(rel_path, source))
        if self.context.config.detect_commented_code:
            findings.extend(self._commented_code(path, rel_path, source))
        return [f for f in findings if self.context.config.rule_enabled(f.rule_id)]

    # ------------------------------------------------------------------
    def _empty_file(self, rel_path: str, source: str) -> list:
        if source.strip() == "":
            return [
                self.make_finding(
                    "empty-file", rel_path, "text",
                    "空文件（没有任何有效内容）",
                    1, whole_file=True, severity=Severity.HIGH, confidence=0.99,
                )
            ]
        return []

    def _backup_file(self, path: Path, rel_path: str, source: str) -> list:
        name = path.name
        for pat in BACKUP_PATTERNS:
            if fnmatch.fnmatch(name, pat):
                return [
                    self.make_finding(
                        "backup-file", rel_path, "text",
                        f"编辑器/版本控制遗留的备份文件（匹配 {pat}）",
                        1, whole_file=True, severity=Severity.MEDIUM, confidence=0.95,
                    )
                ]
        return []

    def _duplicate_file(self, rel_path: str, source: str) -> list:
        digest = sha256_bytes(source.encode("utf-8", errors="replace"))
        if digest in self._hash_owner:
            owner = self._hash_owner[digest]
            return [
                self.make_finding(
                    "duplicate-file", rel_path, "text",
                    f"与 “{owner}” 内容完全相同的重复文件",
                    1, whole_file=True, severity=Severity.HIGH, confidence=0.97,
                )
            ]
        self._hash_owner[digest] = rel_path
        return []

    def _commented_code(self, path: Path, rel_path: str, source: str) -> list:
        ext = path.suffix.lower()
        if ext in _SLASH_LANGS:
            pattern = _SLASH_CODE_RE
        elif ext in _HASH_LANGS:
            pattern = _HASH_CODE_RE
        elif ext in _DASH_LANGS:
            return []  # SQL -- blocks are too noisy; skip
        else:
            return []
        lines = source.splitlines()
        findings = []
        run_start, run_len = None, 0
        for idx, line in enumerate(lines, start=1):
            if pattern.match(line):
                run_start = run_start or idx
                run_len += 1
            else:
                if run_start is not None and run_len >= 3:
                    findings.append(
                        self.make_finding(
                            "commented-code", rel_path, "generic",
                            f"连续 {run_len} 行被注释掉的代码，疑似废弃代码块",
                            run_start, idx - 1, severity=Severity.LOW, confidence=0.5,
                            snippet="\n".join(lines[run_start - 1 : idx - 1][:6]),
                        )
                    )
                run_start, run_len = None, 0
        if run_start is not None and run_len >= 3:
            findings.append(
                self.make_finding(
                    "commented-code", rel_path, "generic",
                    f"连续 {run_len} 行被注释掉的代码，疑似废弃代码块",
                    run_start, len(lines), severity=Severity.LOW, confidence=0.5,
                    snippet="\n".join(lines[run_start - 1 :][:6]),
                )
            )
        return findings
