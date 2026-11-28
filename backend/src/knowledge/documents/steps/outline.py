"""Outline: the heading structure an engine often gets wrong, rebuilt from the text itself.

1. **Table of contents.** A block titled «Índice», «Contenido» or «Tabla de contenido» and the entries after it are
   dropped; so is a run of three or more list items whose numbers reappear later as headings (OpenDataLoader renders
   a table of contents as a list).
2. **Promotion.** A short paragraph that starts with a section number of a family the document already uses for
   headings, or that is entirely bold, becomes a heading (engines often lose heading styles).
3. **Levels from numbering.** Roman chapters are level 1; decimal numbers give their depth with trailing ``.0``
   ignored («8.0» is a chapter, «8.1» its child: ``_number_depth`` in ragVersions-Scale); a letter («a.») sits one level
   under the last numbered heading. Unnumbered headings keep the engine's relative level. The document title is level
   0 and stays out of section paths.
4. **Annexes.** When top-level numbering restarts (an annex with its own 1, 2, 3), the restarted headings get
   ``meta['scope']`` (the last «Anexo» heading, or «Anexo»), so the ``sections`` step nests them under it instead of
   mixing them with the main chapters (``_apply_annex_regression_guard`` in ragVersions-Scale)."""
from __future__ import annotations

import re
import unicodedata

from ..model import Block, NormalizedDocument
from ..registry import STEPS, register
from .base import Step, dropped

NUMBERED = re.compile(r"^(?P<num>\d+(?:\.\d+)*|[IVXLC]+|[a-zA-Z])(?P<sep>\s*[.)]\s*-?\s*|\s*[-–]\s*|\s+)(?P<title>\S.*)$")
TOC_TITLES = {"indice", "indice general", "contenido", "contenidos", "tabla de contenido", "tabla de contenidos",
              "table of contents", "contents"}
TOC_ENTRY = re.compile(r"(\.{3,}|…)\s*\d+\s*$|\s\d{1,3}\s*$")
ANNEX = re.compile(r"\b(?:anexos?|ap[ée]ndices?|annex(?:es)?|appendi(?:x|ces))\b", re.IGNORECASE)
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
# a numbered title followed by its text in one block: «II.- Plaga.- En el contexto…», «4.2 Muestreo: se toman…»
INLINE_TITLE = re.compile(r"^(?P<head>.{3,80}?(?:\.-|:))\s+(?P<body>\S.{20,})$", re.DOTALL)


def _norm(text: str) -> str:
    """Lowercase ASCII words only: «Índice:» -> «indice»."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text).split())


def _roman(s: str) -> int | None:
    s = s.upper()
    if not s or any(ch not in ROMAN for ch in s):
        return None
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = ROMAN[a]
        total += -v if b in ROMAN and ROMAN[b] > v else v
    return total


def numbering(text: str) -> tuple[str, str, int] | None:
    """(family, label, top number) for a numbered heading text: «IV.- Manejo» -> ('roman', 'IV', 4); «4.1.2 Control»
    -> ('decimal', '4.1.2', 4); «a. Objetivo» -> ('letter', 'a', 1). ``None`` if the text is not numbered."""
    m = NUMBERED.match(text.strip())
    if not m:
        return None
    num, sep = m.group("num"), m.group("sep")
    if num.isdigit() or "." in num and num.replace(".", "").isdigit():
        return "decimal", num, int(num.split(".")[0])
    if (r := _roman(num)) is not None and (len(num) > 1 or sep.strip()):
        return "roman", num.upper(), r
    if len(num) == 1 and num.isalpha() and sep.strip():
        return "letter", num.lower(), ord(num.lower()) - 96
    return None


def depth(label: str) -> int:
    parts = label.split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return len(parts)


@register(STEPS, "outline")
class OutlineStep(Step):
    name = "outline"

    # 1. Table of contents ------------------------------------------------------------------------------------------
    def _drop_toc(self, blocks: list[Block]) -> tuple[list[Block], list[tuple[Block, str]]]:
        """Two signals. A block titled «Índice»/«Contenido» drops itself and the entries that follow it. And, because
        engines render a table of contents as a mix of lists and paragraphs, a page with three or more numbered
        entries that reappear on a later page as headings (or as numbered paragraphs) is a table-of-contents page:
        its numbered entries, its dotted-leader lines and its list items are dropped."""
        min_entries = int(self.options.get("toc_min_entries", 3))
        later: dict[int, set[str]] = {}                 # labels numbered on pages after p
        by_page: dict[int, set[str]] = {}
        for b in blocks:
            if b.page is not None and b.kind in ("heading", "paragraph") and (n := numbering(b.text)):
                by_page.setdefault(b.page, set()).add(n[1])
        pages = sorted(by_page)
        for p in {b.page for b in blocks if b.page is not None}:
            later[p] = set().union(*(by_page[q] for q in pages if q > p)) if pages else set()

        toc_pages = set()
        for p, after in later.items():
            entries = [b for b in blocks if b.page == p and (n := numbering(b.text)) and n[1] in after]
            if len(entries) >= min_entries:
                toc_pages.add(p)

        out, removed, i = [], [], 0
        while i < len(blocks):
            b = blocks[i]
            if b.kind in ("heading", "paragraph") and _norm(b.text) in TOC_TITLES:
                removed.append((b, "título de índice"))
                i += 1
                while i < len(blocks) and blocks[i].kind in ("list_item", "paragraph") and (
                        TOC_ENTRY.search(blocks[i].text) or blocks[i].page in toc_pages):
                    removed.append((blocks[i], "entrada de índice"))
                    i += 1
                continue
            if b.page in toc_pages and (b.kind == "list_item" or TOC_ENTRY.search(b.text)
                                        or ((n := numbering(b.text)) and n[1] in later[b.page])):
                removed.append((b, "página de índice"))
                i += 1
                continue
            out.append(b)
            i += 1
        return out, removed

    # 2-4. Promotion, levels and annex scopes -----------------------------------------------------------------------
    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        blocks, removed = self._drop_toc(list(doc.blocks))
        max_chars = int(self.options.get("max_heading_chars", 110))

        # numbers that cannot be section numbers: a decimal far above every chapter number (a value from a table)
        tops = [n[2] for b in blocks if b.kind in ("heading", "paragraph", "list_item") and (n := numbering(b.text))
                and n[0] == "roman"]
        tops += [n[2] for b in blocks if b.kind == "heading" and (n := numbering(b.text)) and n[0] == "decimal"]
        tops.sort()
        ceiling = (tops[len(tops) // 2] if tops else 0) + int(self.options.get("max_number_jump", 8))

        def plausible(n) -> bool:
            return n is not None and not (n[0] == "decimal" and n[2] > ceiling)

        families = {n[0] for b in blocks if b.kind == "heading" and plausible(n := numbering(b.text))}
        promoted = []
        for b in blocks:
            n = numbering(b.text) if b.kind in ("paragraph", "list_item") else None
            numbered = plausible(n) and n[0] in families
            if b.kind == "heading" and numbering(b.text) and not plausible(numbering(b.text)):
                promoted.append(b.with_(kind="paragraph", level=None, meta={**b.meta, "demoted": "número inverosímil"}))
            elif numbered and (m := INLINE_TITLE.match(b.text)) and len(m.group("head")) <= max_chars:
                # «II.- Plaga.- En el contexto…»: the heading and its first paragraph were extracted as one block
                promoted.append(b.with_(kind="heading", text=m.group("head").strip(), level=99,
                                        meta={**b.meta, "promoted": True, "split_inline": True, "was": b.kind}))
                promoted.append(b.with_(kind="paragraph", text=m.group("body").strip(), level=None, meta={}))
            elif b.kind in ("paragraph", "list_item") and len(b.text) <= max_chars and (numbered or (
                    b.kind == "paragraph" and b.meta.get("bold"))):
                promoted.append(b.with_(kind="heading", level=99, meta={**b.meta, "promoted": True, "was": b.kind}))
            else:
                promoted.append(b)
        blocks = promoted

        headings = [b for b in blocks if b.kind == "heading"]
        # the shallowest decimal depth decides whether decimals sit under roman chapters; headings the engine marked
        # count first, since a promoted «1.» may still turn out to be a list item
        trusted = [b for b in headings if not b.meta.get("promoted")] or headings
        decimal_min = min((depth(n[1]) for b in trusted if (n := numbering(b.text)) and n[0] == "decimal"), default=1)
        has_roman = any((n := numbering(b.text)) and n[0] == "roman" for b in headings)
        offset = 1 if has_roman and decimal_min == 1 else 0
        unnumbered = [b.level for b in headings if not numbering(b.text) and not b.meta.get("title") and b.level]
        base = min(unnumbered, default=1)

        # the document title: marked by the engine, or the first heading when it is unnumbered, on the first page, and
        # numbered chapters follow (OpenDataLoader marks it; its Markdown does not)
        first = next((i for i, b in enumerate(blocks) if b.kind == "heading"), None)
        title_idx = None
        if first is not None and not any(b.meta.get("title") for b in headings):
            fb = blocks[first]
            if not numbering(fb.text) and fb.page in (None, 1) and any(
                    numbering(b.text) for b in blocks[first + 1:] if b.kind == "heading"):
                title_idx = first

        out, last_level, last_top, annex_label, parts = [], 1, None, None, 0
        chapter = None                                    # number of the current chapter (roman value or decimal top)
        for idx, b in enumerate(blocks):
            if b.kind == "heading" and b.meta.get("promoted") and chapter is not None and has_roman:
                n = numbering(b.text)
                # a promoted decimal must belong to the current chapter: inside chapter VII, «7.1» is a section but «2.»
                # is an item of a numbered list (a bibliography, steps)
                if n and n[0] == "decimal" and n[2] != chapter:
                    original = "list_item" if b.meta.get("was") == "list_item" else "paragraph"
                    out.append(b.with_(kind=original, level=1 if original == "list_item" else None,
                                       meta={**b.meta, "promoted": False, "demoted": "fuera del capítulo"}))
                    continue
            if b.kind == "heading" and (n := numbering(b.text)) and n[0] == "roman":
                chapter = n[2]
            if b.kind == "caption" and len(b.text) > int(self.options.get("max_caption_chars", 200)):
                out.append(b.with_(kind="paragraph"))       # engines label some long paragraphs as captions
                continue
            if b.kind != "heading":
                out.append(b)
                continue
            if b.meta.get("title") or idx == title_idx:
                out.append(b.with_(level=0, meta={**b.meta, "title": True}))
                continue
            n = numbering(b.text)
            meta = dict(b.meta)
            if n and n[0] == "roman":
                level = 1
            elif n and n[0] == "decimal":
                level = depth(n[1]) + offset
            elif n and n[0] == "letter":
                level = last_level + 1
            else:
                level = max(1, (b.level or base) - base + 1) if (b.level or 0) < 99 else last_level + 1
            if level == 1 and n and n[0] in ("roman", "decimal"):
                if last_top is not None and n[2] < last_top:
                    parts += 1
                    meta["scope"] = (annex_label or "Anexo") + (f" (parte {parts})" if parts > 1 else "")
                last_top = n[2]
                if ANNEX.search(b.text):
                    annex_label, parts = b.text, 0
            elif level == 1 and ANNEX.search(b.text):
                # an unnumbered «ANEXO A»: the next restart of the chapter numbering belongs to it
                annex_label, parts = b.text, 0
            if n and n[0] != "letter":
                last_level = level
            out.append(b.with_(level=level, meta=meta))
        return doc.with_blocks(out, **dropped(doc, self.name, removed))
