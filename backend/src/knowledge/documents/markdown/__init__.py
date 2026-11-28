"""Markdown as a route and as a rendering. Pages travel as ``<!-- page N -->`` anchors, so Markdown can carry
citations through a round trip: ``parse(render(doc))`` keeps kinds, text, pages and heading levels."""
from .parse import parse_markdown
from .render import render_markdown, table_markdown

__all__ = ["parse_markdown", "render_markdown", "table_markdown"]
