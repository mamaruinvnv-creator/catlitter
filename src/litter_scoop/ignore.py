"""Ignore-rule handling: built-in skips plus lightweight ``.gitignore`` support.

The matcher intentionally implements the *common* gitignore subset (directory
markers, ``*``/``?`` globbing, ``**``, negation) without third-party deps.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

#: Directories that are never scanned, regardless of .gitignore.
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".litter-box",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".idea",
    ".vscode",
    "vendor",
    "target",
    ".turbo",
}

#: File globs that are never scanned (binaries, lockfiles, generated files).
DEFAULT_IGNORE_FILES = {
    "*.pyc",
    "*.pyo",
    "*.class",
    "*.jar",
    "*.war",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.webp",
    "*.svg",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.tgz",
    "*.rar",
    "*.7z",
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.o",
    "*.a",
    "*.bin",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    # NOTE: *.bak / *.orig / *.old / *~ / *.swp are NOT ignored here on
    # purpose — the generic adapter flags them as "backup-file" waste.
}


@dataclass(slots=True)
class _Rule:
    pattern: str
    negation: bool
    directory_only: bool
    base: str  # directory the rule applies to, posix style, "" = root


@dataclass(slots=True)
class IgnoreMatcher:
    root: Path
    rules: list[_Rule] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path, extra_patterns: list[str] | None = None) -> IgnoreMatcher:
        matcher = cls(root=root)
        for candidate in (root / ".gitignore", root / ".litterignore"):
            if candidate.is_file():
                matcher._read_file(candidate)
        for pattern in extra_patterns or []:
            matcher._add_rule(pattern, base="")
        return matcher

    def _read_file(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        base = ""
        if path.name == ".litterignore":
            base = ""
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            self._add_rule(line, base=base)

    def _add_rule(self, raw: str, base: str) -> None:
        negation = raw.startswith("!")
        pattern = raw[1:] if negation else raw
        directory_only = pattern.endswith("/")
        if directory_only:
            pattern = pattern[:-1]
        # Patterns containing a slash (other than trailing) are rooted.
        anchored = "/" in pattern
        if pattern.startswith("/"):
            pattern = pattern[1:]
        self.rules.append(
            _Rule(
                pattern=pattern,
                negation=negation,
                directory_only=directory_only,
                base=base if anchored else "",
            )
        )

    @staticmethod
    def _matches(rel_posix: str, is_dir: bool, rule: _Rule) -> bool:
        if rule.directory_only and not is_dir:
            # A directory rule also matches everything beneath that dir.
            pass
        target = rel_posix
        if rule.base:
            target = os.path.relpath(rel_posix, rule.base).replace(os.sep, "/")
            if target.startswith("../"):
                return False
        if "**" in rule.pattern:
            # Translate ** into fnmatch-friendly wildcard.
            pat = rule.pattern.replace("**/", "*/").replace("/**", "/*")
            if fnmatch.fnmatch(target, pat) or fnmatch.fnmatch(
                target, rule.pattern.replace("**", "*")
            ):
                return True
        if "/" in rule.pattern:
            if fnmatch.fnmatch(target, rule.pattern):
                return True
        else:
            # Bare name matches at any depth.
            parts = target.split("/")
            name = parts[-1]
            if fnmatch.fnmatch(name, rule.pattern):
                return True
            # Directory rule matches any path component.
            if rule.directory_only:
                for part in parts[:-1]:
                    if fnmatch.fnmatch(part, rule.pattern):
                        return True
        return False

    def is_ignored(self, path: Path, is_dir: bool = False) -> bool:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            rel = Path(path.name)
        rel_posix = PurePosixPath(*rel.parts).as_posix() if rel.parts else ""
        parts = rel_posix.split("/") if rel_posix else []

        # Built-in directory / file skips.
        if is_dir and path.name in DEFAULT_IGNORE_DIRS:
            return True
        if not is_dir:
            for pat in DEFAULT_IGNORE_FILES:
                if fnmatch.fnmatch(path.name, pat):
                    return True
        if any(part in DEFAULT_IGNORE_DIRS for part in parts[:-1]):
            return True

        verdict = False
        for rule in self.rules:
            if self._matches(rel_posix, is_dir, rule):
                verdict = not rule.negation
        return verdict


def walk_source_files(root: Path, matcher: IgnoreMatcher) -> list[Path]:
    """Yield every non-ignored regular file beneath *root*, sorted."""
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        kept_dirs = []
        for name in dirnames:
            child = here / name
            if not matcher.is_ignored(child, is_dir=True):
                kept_dirs.append(name)
        dirnames[:] = sorted(kept_dirs)
        for name in sorted(filenames):
            child = here / name
            if child.is_file() and not matcher.is_ignored(child, is_dir=False):
                collected.append(child)
    return collected
