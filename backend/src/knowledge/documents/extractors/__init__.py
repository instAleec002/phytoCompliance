"""Extractor adapters. Importing this package registers every engine; heavy engines import their library only when a
document is actually read, so registering them costs nothing."""
from . import docling, docx, opendataloader, pymupdf, xlsx  # noqa: F401  (registration)
from .base import Extractor, UnsupportedFormat

__all__ = ["Extractor", "UnsupportedFormat"]
