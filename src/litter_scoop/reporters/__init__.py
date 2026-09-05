"""Report renderers: terminal text, JSON, and a standalone HTML report."""

from .html import render_html
from .json_reporter import render_json
from .text import render_text

__all__ = ["render_html", "render_json", "render_text"]
