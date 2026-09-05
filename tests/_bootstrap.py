"""Shared test bootstrap: make src/ importable without installation."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "sample_project"
