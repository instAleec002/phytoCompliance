"""IRAC MoA Classification Scheme (PDF), Appendix 5: every classified active ingredient in alphabetical order with its
group. IRAC calls it "the only authoritative and comprehensive list". The plain text layout shifts rows on some
pages, so the table is read from the word positions (pdfplumber), two columns of (ingredient, group) per page.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import MoaEntry, normalize_code

_CODE = re.compile(r"^(?:\d{1,2}[A-G]?|UN[A-Z]?)$")


def parse_rows(tables: list[list[list[str | None]]]) -> list[MoaEntry]:
    entries: list[MoaEntry] = []
    for table in tables:
        if not table or "Active Ingredient" not in (table[0][0] or ""):
            continue
        for row in table[1:]:
            for i in range(0, len(row) - 1, 2):       # (name, code) pairs, one or two per row
                for name, code in _pairs(row[i] or "", row[i + 1] or ""):
                    entries.append(MoaEntry(scheme="IRAC", code=normalize_code(code), name=name.rstrip(",")))
    return entries


def _pairs(name_cell: str, code_cell: str) -> list[tuple[str, str]]:
    """A cell may hold two rows merged ("Ethiofencarb / Ethion" with "1A / 1B" on two lines), or one name wrapped over
    two lines with a single code ("Bioallethrin S-cyclopentenyl / isomer" with "3A")."""
    names = [" ".join(n.split()) for n in name_cell.splitlines() if n.strip()]
    codes = [c.strip() for c in code_cell.splitlines() if c.strip()]
    if not names or not codes or not all(_CODE.match(c) for c in codes):
        return []
    if len(codes) == 1:
        return [(" ".join(names), codes[0])]
    if len(names) == len(codes):
        return list(zip(names, codes))
    raise ValueError(f"IRAC cell that cannot be paired: {names} / {codes}")


def appendix_pages(pdf) -> range:
    """Pages from "Appendix 5" up to "Appendix 6"."""
    start = end = None
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if start is None and "ACTIVE INGREDIENTS (ALPHABETICAL ORDER)" in text.upper():
            start = i
        elif start is not None and "Appendix 6" in text and "Pending Registration" in text:
            end = i
            break
    if start is None or end is None:
        raise ValueError("IRAC PDF without Appendix 5: the layout changed")
    return range(start, end)


def parse_irac(path: Path) -> list[MoaEntry]:
    with pdfplumber.open(path) as pdf:
        tables = [t for i in appendix_pages(pdf) for t in pdf.pages[i].extract_tables()]
    return parse_rows(tables)
