"""Chunkers. Importing the package registers them: ``structural`` (default), ``fixed`` and ``page`` (ablation
baselines) and ``parent_child``."""
from . import fixed, page, parent_child, structural  # noqa: F401  (registration)
from .base import Chunker, block_text, sentences
from .header import add_headers, header_for

__all__ = ["Chunker", "add_headers", "block_text", "header_for", "sentences"]
