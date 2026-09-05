"""Adapter registry."""

from __future__ import annotations

from .base import AnalysisContext, BaseAdapter
from .generic_adapter import GenericAdapter
from .python_adapter import PythonAdapter
from .web_adapter import WebAdapter

REGISTRY: dict[str, type[BaseAdapter]] = {
    PythonAdapter.name: PythonAdapter,
    WebAdapter.name: WebAdapter,
    GenericAdapter.name: GenericAdapter,
}

__all__ = ["AnalysisContext", "BaseAdapter", "REGISTRY", "GenericAdapter", "PythonAdapter", "WebAdapter"]
