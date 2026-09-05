"""Core data models for Litter Scoop.

The "cat-litter model" treats redundant code as waste:

* a :class:`Finding` is one piece of waste the scanner spotted;
* a :class:`ProjectProfile` describes the project so the right adapters are
  picked automatically;
* a :class:`BagBatch` is one sealed garbage-bag holding everything that was
  scooped during a single run, so it can be restored later.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class Severity(str, enum.Enum):
    """How confident we are that a finding is genuinely safe to remove."""

    #: Heuristic hit, a human should eyeball it.
    LOW = "low"
    #: Very likely dead code (e.g. unreachable statement).
    MEDIUM = "medium"
    #: Almost certainly waste (e.g. empty file, duplicate file).
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]


@dataclass(frozen=True, slots=True)
class Finding:
    """A single redundant-code candidate located in a file.

    Line numbers are 1-based and inclusive. When ``whole_file`` is ``True``
    the scoop operation removes the whole file instead of a line range.
    """

    rule_id: str
    path: str
    language: str
    message: str
    start_line: int = 0
    end_line: int = 0
    symbol: str = ""
    severity: Severity = Severity.LOW
    confidence: float = 0.5
    snippet: str = ""
    whole_file: bool = False
    adapter: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["severity"] = self.severity.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        data = dict(data)
        data["severity"] = Severity(data.get("severity", "low"))
        return cls(**data)

    @property
    def line_span(self) -> int:
        if self.whole_file or self.start_line == 0:
            return 0
        return self.end_line - self.start_line + 1


@dataclass(slots=True)
class ProjectProfile:
    """Fingerprint of the scanned project used for adapter auto-selection."""

    root: Path
    project_types: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)  # ext -> line count
    marker_files: list[str] = field(default_factory=list)
    adapters: list[str] = field(default_factory=list)

    @property
    def primary_language(self) -> str:
        if not self.languages:
            return "unknown"
        return max(self.languages.items(), key=lambda kv: kv[1])[0]

    def summary(self) -> str:
        bits = [f"primary={self.primary_language}"]
        if self.project_types:
            bits.append("types=" + ",".join(self.project_types))
        if self.frameworks:
            bits.append("frameworks=" + ",".join(self.frameworks))
        bits.append("adapters=" + ",".join(self.adapters))
        return " | ".join(bits)


@dataclass(slots=True)
class StashedItem:
    """One piece of waste stored inside a garbage bag."""

    finding: Finding
    original_path: str          # project-relative path of the source file
    stored_path: str            # bag-relative path of the pristine backup
    original_sha256: str        # hash of the file *before* scooping
    action: str                 # "line-edit" | "delete-file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.to_dict(),
            "original_path": self.original_path,
            "stored_path": str(self.stored_path) if self.stored_path else "",
            "original_sha256": self.original_sha256,
            "action": self.action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StashedItem:
        return cls(
            finding=Finding.from_dict(data["finding"]),
            original_path=data["original_path"],
            stored_path=data["stored_path"],
            original_sha256=data["original_sha256"],
            action=data["action"],
        )


@dataclass(slots=True)
class BagBatch:
    """A sealed garbage-bag: metadata + every item scooped in one run."""

    batch_id: str
    created_at: str
    root: str
    items: list[StashedItem] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "created_at": self.created_at,
            "root": self.root,
            "note": self.note,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BagBatch:
        return cls(
            batch_id=data["batch_id"],
            created_at=data["created_at"],
            root=data.get("root", ""),
            note=data.get("note", ""),
            items=[StashedItem.from_dict(i) for i in data.get("items", [])],
        )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 16) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
