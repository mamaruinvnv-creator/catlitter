"""Project fingerprinting and automatic adapter selection.

This is the "auto-fit" layer: instead of asking the user what kind of project
they have, Litter Scoop inspects marker files (``pyproject.toml``,
``package.json`` ...), measures language composition and then activates the
matching set of redundancy detectors.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from .ignore import IgnoreMatcher, walk_source_files

# extension -> (language key, owning adapter)
EXTENSION_LANGUAGE: dict[str, tuple[str, str]] = {
    ".py": ("python", "python"),
    ".pyi": ("python", "python"),
    ".js": ("javascript", "web"),
    ".jsx": ("javascript", "web"),
    ".mjs": ("javascript", "web"),
    ".cjs": ("javascript", "web"),
    ".ts": ("typescript", "web"),
    ".tsx": ("typescript", "web"),
    ".vue": ("vue", "web"),
    ".svelte": ("svelte", "web"),
    ".go": ("go", "generic"),
    ".java": ("java", "generic"),
    ".kt": ("kotlin", "generic"),
    ".c": ("c", "generic"),
    ".h": ("c", "generic"),
    ".cpp": ("cpp", "generic"),
    ".cc": ("cpp", "generic"),
    ".cxx": ("cpp", "generic"),
    ".hpp": ("cpp", "generic"),
    ".cs": ("csharp", "generic"),
    ".rs": ("rust", "generic"),
    ".rb": ("ruby", "generic"),
    ".php": ("php", "generic"),
    ".swift": ("swift", "generic"),
    ".sh": ("shell", "generic"),
    ".bash": ("shell", "generic"),
    ".sql": ("sql", "generic"),
}

TEXT_EXTENSIONS = set(EXTENSION_LANGUAGE) | {
    ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg",
    ".html", ".htm", ".css", ".scss", ".less", ".xml", ".gradle", ".dockerfile",
}

# marker filename -> project type label
PROJECT_MARKERS: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "package.json": "node",
    "bun.lockb": "node",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "jvm-maven",
    "build.gradle": "jvm-gradle",
    "build.gradle.kts": "jvm-gradle",
    "composer.json": "php",
    "Gemfile": "ruby",
    "CMakeLists.txt": "cmake",
    "Makefile": "make",
    "*.csproj": "dotnet",
}

ADAPTER_ORDER = ("python", "web", "generic")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_frameworks(root: Path) -> list[str]:
    frameworks: list[str] = []
    pkg = root / "package.json"
    if pkg.is_file():
        data = _read_json(pkg)
        dep_names: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            dep_names.update(data.get(key, {}).keys())
        table = {
            "react": "react",
            "react-dom": "react",
            "next": "next.js",
            "vue": "vue",
            "nuxt": "nuxt",
            "@angular/core": "angular",
            "svelte": "svelte",
            "express": "express",
            "vite": "vite",
        }
        found = sorted({tag for dep, tag in table.items() if dep in dep_names})
        frameworks.extend(found)
    req = root / "requirements.txt"
    if req.is_file():
        try:
            text = req.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            text = ""
        for needle, tag in (
            ("django", "django"),
            ("flask", "flask"),
            ("fastapi", "fastapi"),
            ("sqlalchemy", "sqlalchemy"),
        ):
            if needle in text:
                frameworks.append(tag)
    return frameworks


def profile_project(
    root: Path,
    matcher: IgnoreMatcher,
    disabled_adapters: set[str] | None = None,
) -> tuple[list[Path], "object"]:
    """Walk *root*, measure the project and pick adapters.

    Returns the list of scannable text files and a :class:`ProjectProfile`.
    """
    from .models import ProjectProfile  # local import avoids cycle at import time

    disabled_adapters = disabled_adapters or set()
    all_files = walk_source_files(root, matcher)

    marker_files: list[str] = []
    project_types: list[str] = []
    for marker, label in PROJECT_MARKERS.items():
        if "*" in marker:
            prefix, suffix = marker.strip("*").split(".", 1)
            hits = [p for p in root.glob(f"*.{suffix}")] if not prefix else []
            if hits:
                marker_files.append(marker)
                project_types.append(label)
        elif (root / marker).exists():
            marker_files.append(marker)
            project_types.append(label)

    language_lines: dict[str, int] = {}
    scannable: list[Path] = []
    adapters_needed: set[str] = set()

    for path in all_files:
        ext = path.suffix.lower()
        is_backup_leftover = any(
            fnmatch.fnmatch(path.name, pat)
            for pat in ("*.bak", "*.orig", "*.old", "*~", "*.swp", "*.swo", "*.tmp", "*.rej")
        )
        if ext not in TEXT_EXTENSIONS and not is_backup_leftover:
            continue
        scannable.append(path)
        if ext in EXTENSION_LANGUAGE:
            language, adapter = EXTENSION_LANGUAGE[ext]
            try:
                with path.open("rb") as fh:
                    line_count = sum(1 for _ in fh)
            except OSError:
                line_count = 0
            language_lines[language] = language_lines.get(language, 0) + line_count
            if adapter not in disabled_adapters:
                adapters_needed.add(adapter)

    # Generic checks (empty files, duplicates, backup files) run for any
    # text-bearing project.
    if scannable and "generic" not in disabled_adapters:
        adapters_needed.add("generic")

    adapters = [a for a in ADAPTER_ORDER if a in adapters_needed]
    profile = ProjectProfile(
        root=root,
        project_types=sorted(set(project_types)),
        frameworks=detect_frameworks(root),
        languages=dict(sorted(language_lines.items(), key=lambda kv: -kv[1])),
        marker_files=marker_files,
        adapters=adapters,
    )
    return scannable, profile
