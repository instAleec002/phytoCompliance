"""Contextual header: the document title and the section path, prepended to a chunk for embedding (``embedding_text``)
and shown with its citation, but never stored as part of the chunk text. It gives each chunk the context that late
chunking would have given, without depending on the encoder's pooling (decision D3, 06/11/2026). Keeping the header
out of the stored text follows ragVersions-Scale (``assemble_embedded_text``).

Format: ``Documento: <title>`` and, when there is one, ``Sección: <a> > <b>``."""
from __future__ import annotations

from dataclasses import replace

from ..model import Chunk, NormalizedDocument


def header_for(doc: NormalizedDocument, section: tuple[str, ...], mode: str | None = None) -> str:
    """`mode="short"` (V3): only the last two section levels, so the header weighs less than the content."""
    lines = [f"Documento: {doc.title}"]
    if mode == "short":
        section = section[-2:]
    if section:
        lines.append("Sección: " + " > ".join(section))
    return "\n".join(lines)


def add_headers(doc: NormalizedDocument, chunks: list[Chunk], mode: str | None = None) -> list[Chunk]:
    return [replace(c, header=header_for(doc, c.section, mode)) for c in chunks]
