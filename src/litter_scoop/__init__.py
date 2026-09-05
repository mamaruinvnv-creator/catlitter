"""Litter Scoop — the cat-litter model for redundant-code cleanup.

Scan a project, scoop redundant code into a restorable garbage bag, keep a
manifest of every removed piece, and either restore it or throw it away.
"""

from __future__ import annotations

__version__ = "0.2.0"

from .engine import ScanResult, scan_project
from .janitor import (
    JanitorBag,
    JanitorScan,
    default_bag_dir,
    scan_system,
)
from .scoop import GarbageBag

__all__ = [
    "scan_project",
    "ScanResult",
    "GarbageBag",
    "JanitorBag",
    "JanitorScan",
    "scan_system",
    "default_bag_dir",
    "__version__",
]
