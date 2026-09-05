"""Configuration loading for ``litterbox.toml``.

The config is optional; every field has a safe default. TOML is parsed with
the stdlib (Python 3.11+ ``tomllib``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAMES = ("litterbox.toml", ".litterbox.toml")


@dataclass(slots=True)
class Config:
    #: Directory name of the garbage bag, created at the project root.
    bag_dir: str = ".litter-box"
    #: Minimum severity that ``scoop`` will act on ("low"|"medium"|"high").
    min_severity: str = "low"
    #: Rule ids that are turned off entirely.
    disable_rules: set[str] = field(default_factory=set)
    #: Only these rule ids run (empty == all enabled).
    enable_only: set[str] = field(default_factory=set)
    #: Extra glob patterns to exclude.
    exclude: list[str] = field(default_factory=list)
    #: Explicitly include globs (applied before exclude).
    include: list[str] = field(default_factory=list)
    #: Adapters that must not run.
    disable_adapters: set[str] = field(default_factory=set)
    #: Require a clean git working tree before scooping (recommended).
    require_clean_git: bool = True
    #: Detect commented-out code blocks (heuristic, can be noisy).
    detect_commented_code: bool = True
    #: Max bytes of a text file we are willing to parse.
    max_file_bytes: int = 2_000_000

    def rule_enabled(self, rule_id: str) -> bool:
        if rule_id in self.disable_rules:
            return False
        if self.enable_only and rule_id not in self.enable_only:
            return False
        return True

    @classmethod
    def load(cls, root: Path) -> Config:
        cfg = cls()
        for name in CONFIG_FILENAMES:
            candidate = root / name
            if candidate.is_file():
                cfg._merge_file(candidate)
                break
        return cfg

    def _merge_file(self, path: Path) -> None:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        section = raw.get("litterbox", raw)  # allow flat or [litterbox] table
        rules = raw.get("rules", {})
        adapters = raw.get("adapters", {})

        if "bag_dir" in section:
            self.bag_dir = str(section["bag_dir"])
        if "min_severity" in section:
            self.min_severity = str(section["min_severity"]).lower()
        if "require_clean_git" in section:
            self.require_clean_git = bool(section["require_clean_git"])
        if "detect_commented_code" in section:
            self.detect_commented_code = bool(section["detect_commented_code"])
        if "max_file_bytes" in section:
            self.max_file_bytes = int(section["max_file_bytes"])
        if "exclude" in section:
            self.exclude = [str(x) for x in section["exclude"]]
        if "include" in section:
            self.include = [str(x) for x in section["include"]]

        self.disable_rules = {
            str(rid) for rid, enabled in rules.items() if not enabled
        }
        self.enable_only = {
            str(rid) for rid, enabled in rules.items() if enabled is True
        } if all(v is True for v in rules.values()) and rules else set()
        self.disable_adapters = {
            str(aid) for aid, enabled in adapters.items() if not enabled
        }


EXAMPLE_CONFIG = """# litter-scoop configuration (put this at your project root)
[litterbox]
bag_dir = ".litter-box"          # 垃圾袋目录
min_severity = "low"             # low | medium | high
require_clean_git = true         # 铲入垃圾袋前要求 git 工作区干净
detect_commented_code = true
exclude = ["docs/**", "migrations/**"]

# Turn individual rules on/off.
[rules]
# "commented-code" = false
# "unused-import" = false

# Turn whole adapters off.
[adapters]
# "web" = false
"""
