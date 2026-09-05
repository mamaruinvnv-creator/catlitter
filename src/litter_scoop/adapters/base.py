"""Adapter contract shared by every redundancy detector."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config
from ..models import Finding


@dataclass(slots=True)
class AnalysisContext:
    """Project-wide state handed to every adapter."""

    root: Path
    files: list[Path]
    relpaths: dict[Path, str]
    config: Config
    #: Every bare name referenced anywhere in the project (cross-file index).
    global_name_refs: dict[str, int] = field(default_factory=dict)
    #: Set of file-relative paths that look like tests (relaxed rules apply).
    test_paths: set[str] = field(default_factory=set)

    def rel(self, path: Path) -> str:
        return self.relpaths.get(path, path.name)

    def is_test_file(self, rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/").lower()
        if normalized in self.test_paths:
            return True
        parts = normalized.split("/")
        return (
            "tests" in parts
            or "test" in parts
            or any(p.startswith("test_") for p in parts)
        )


class BaseAdapter:
    """Base class. Sub-classes implement :meth:`analyze`."""

    name: str = "base"
    extensions: tuple[str, ...] = ()

    def __init__(self, context: AnalysisContext) -> None:
        self.context = context

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def analyze(self, path: Path, rel_path: str, source: str) -> list[Finding]:  # noqa: D401
        raise NotImplementedError

    # -- helpers ---------------------------------------------------------
    def make_finding(
        self,
        rule_id: str,
        rel_path: str,
        language: str,
        message: str,
        start_line: int,
        end_line: int | None = None,
        *,
        symbol: str = "",
        severity= None,
        confidence: float = 0.5,
        snippet: str = "",
        whole_file: bool = False,
    ) -> Finding:
        from ..models import Severity

        if not self.context.config.rule_enabled(rule_id):
            # Caller checks too, but this keeps adapters terse.
            pass
        return Finding(
            rule_id=rule_id,
            path=rel_path,
            language=language,
            message=message,
            start_line=start_line,
            end_line=end_line if end_line is not None else start_line,
            symbol=symbol,
            severity=severity or Severity.LOW,
            confidence=confidence,
            snippet=snippet,
            whole_file=whole_file,
            adapter=self.name,
        )
