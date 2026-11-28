"""Text normalization: Unicode NFC, Symbol-font private characters, ligatures, soft hyphens, line breaks written as
``<br>``, words cut at a line end ("fitosani- tario"), and whitespace. Applies to every block and every table cell.

Code points are written with ``chr()`` on purpose: these characters are invisible or look like their replacement,
and as literals they would be unreadable in the source."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from ..model import NormalizedDocument
from ..registry import STEPS, register
from .base import Step

# Symbol and Wingdings fonts put their glyphs in the private use area; PDFs then carry these codes for bullets and
# arrows (mapping from ragVersions-Scale, normalize_symbol_font_chars).
PRIVATE_USE = {chr(0xF0B7): "•", chr(0xF0A7): "▪", chr(0xF0D8): "►", chr(0xF06F): "○", chr(0xF0A8): "§",
               chr(0xF0E4): "™", chr(0xF0FC): "✓", chr(0xF0E0): "→", chr(0xF0AD): "-"}
LIGATURES = {chr(0xFB00): "ff", chr(0xFB01): "fi", chr(0xFB02): "fl", chr(0xFB03): "ffi", chr(0xFB04): "ffl",
             chr(0xFB05): "st"}
SOFT_HYPHEN = chr(0x00AD)
HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# a word split at a line end: two or more letters, hyphen, space, two or more lowercase letters
CUT_WORD = re.compile(r"(?<=[a-záéíóúñü]{2})- (?=[a-záéíóúñü]{2})")
# spaces, tabs, no-break space and the U+2000..U+200B space family
SPACES = re.compile("[ \t" + chr(0x00A0) + chr(0x2000) + "-" + chr(0x200B) + "]+")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = HTML_BREAK.sub(" ", text)                 # engines write line breaks inside table cells as <br>
    for a, b in {**PRIVATE_USE, **LIGATURES}.items():
        text = text.replace(a, b)
    text = text.replace(SOFT_HYPHEN, "")
    text = CUT_WORD.sub("", text)
    text = SPACES.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


@register(STEPS, "text")
class TextStep(Step):
    name = "text"

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        blocks = []
        for b in doc.blocks:
            cells = tuple(replace(c, text=clean(c.text)) for c in b.cells)
            text = clean(b.text)
            if text or cells:
                blocks.append(b.with_(text=text, cells=cells))
        return doc.with_blocks(blocks)
