"""40 CFR Part 180 (eCFR XML): pesticide tolerances (subpart C) and exemptions from the requirement of a tolerance
(subpart D).

Each section is one substance: "§ 180.582 Pyraclostrobin; tolerances for residues." Its tables list commodity and
parts per million (ppm = mg/kg), sometimes with an expiration or revocation date, under the paragraph they belong to:
(a) general, (b) time-limited tolerances for Section 18 emergency exemptions, (c) tolerances with regional
registrations, (d) indirect or inadvertent residues. Footnote marks (``<SU>``) are dropped from the cell text.

Two general sections exempt active ingredients and are read with their own rules: 180.905 (pesticide chemicals
applied to growing crops: petroleum oils, pyrethrins...) and 180.950 (minimal risk substances: the table of specific
chemicals in paragraph (e), plus the categories "commonly consumed food commodities" and "edible fats and oils").
Left out: definitions and procedure (180.1 to 180.99), the crop group tables (180.40, 180.41), and the exemptions for
inert ingredients, antimicrobial formulations and polymers (180.910 to 180.940, 180.960).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from .models import UsExemption, UsSection, UsTolerance

_PARAGRAPH = re.compile(r"^\(([a-e])\)")
_SUBPARAGRAPH = re.compile(r"^\([a-e]\)\s*(?:<I>.*?</I>\.?\s*)?\((\d+)\)")
PARAGRAPH_KIND = {"a": "general", "b": "section_18", "c": "regional", "d": "indirect", "e": "other"}
# section numbers after "180." that are not substance tolerances (definitions, crop groups, inert lists)
SKIPPED_RANGES = ((0, 99), (40, 41), (900, 904), (906, 949), (951, 999))
EXEMPTION_TEXT_CHARS = 3000


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    parts = [el.text or ""]
    for child in el:
        if child.tag != "SU":                       # footnote mark
            parts.append(_text(child))
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def _skipped(number: str) -> bool:
    """"180.1011" is section 1011, not a decimal: compare the integer after the dot."""
    m = re.match(r"^180\.(\d+)", number)
    if not m:
        return True
    n = int(m.group(1))
    return any(lo <= n <= hi for lo, hi in SKIPPED_RANGES)


_KIND_SEPARATOR = re.compile(r"[;,]\s*(?=(?:temporary\s+)?(?:tolerance|exempt))", re.IGNORECASE)
# a heading without separator: "...benzenamine tolerances for residues." (180.527)
_KIND_PHRASE = re.compile(r"\s+(?=(?:tolerances? for residues|exemption from the requirement))", re.IGNORECASE)


def substance_of(head: str) -> tuple[str, str] | None:
    """('Pyraclostrobin', 'tolerance') from "§ 180.582 Pyraclostrobin; tolerances for residues.". Some headings use a
    comma instead of the semicolon ("§ 180.503 Cymoxanil, tolerance for residues."); the last separator before
    "tolerance(s)" or "exemption(s)" ends the name."""
    m = re.match(r"^§+\s*[\d.a-z-]+\s+(.*)$", head.strip())
    if not m:
        return None
    body = m.group(1).rstrip(".")
    separators = list(_KIND_SEPARATOR.finditer(body)) or list(_KIND_PHRASE.finditer(body))
    if not separators:
        return None
    cut = separators[-1]
    name, rest = body[:cut.start()].strip(), body[cut.end():].lower()
    return (name, "exemption") if "exempt" in rest else (name, "tolerance")


def parse_ppm(text: str) -> float | None:
    """'4.0' -> 4.0; '0.1(N)' (the former "negligible residue" mark) -> 0.1; '4.0 1' and '1 7.0' (a footnote number
    written as text next to the value) -> 4.0 and 7.0; '0.01 ppm' -> 0.01; '.5' -> 0.5; '6. 0' -> 6.0. Anything else
    ('*') has no value; the original text is always kept."""
    t = text.replace(",", "").replace("(N)", "").replace("ppm", "").strip()
    if re.fullmatch(r"\d+\.\s\d+", t):
        t = t.replace(" ", "")
    tokens = t.split()
    if len(tokens) == 2:
        decimals = [x for x in tokens if "." in x]
        footnotes = [x for x in tokens if re.fullmatch(r"[1-9]", x)]
        if len(decimals) == 1 and len(footnotes) == 1:
            tokens = decimals
    if len(tokens) == 1 and re.fullmatch(r"\d*\.?\d+", tokens[0]):
        return float(tokens[0])
    return None


def _to_date(text: str) -> date | None:
    text = text.strip().rstrip(".")
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _table_rows(table: ET.Element) -> tuple[list[str], list[list[str]]]:
    header = [_text(th).lower().replace(" ", "") for th in table.iter("TH")]
    rows = [[_text(td) for td in tr.findall("TD")] for tr in table.iter("TR")]
    return header, [r for r in rows if r]


def parse_180_905(div: ET.Element) -> list[UsSection]:
    """Items "(1) Petroleum oils." of paragraph (a), each with the conditions of the section."""
    head = _text(div.find("HEAD"))
    full = " ".join(_text(p) for p in div.iter("P"))
    out = []
    for p in div.iter("P"):
        if m := re.match(r"^\((\d+)\)\s+(.+?)\.?$", _text(p)):
            out.append(UsSection(number="180.905", substance=m.group(2), kind="exemption", heading=head,
                                 exemption=UsExemption(text=full[:EXEMPTION_TEXT_CHARS])))
    return out


def parse_180_950(div: ET.Element) -> list[UsSection]:
    """Paragraph (e): one exemption per chemical of the table; plus the two categories that name no chemical."""
    head = _text(div.find("HEAD"))
    paragraphs = [_text(p) for p in div.iter("P")]
    intro = paragraphs[0] if paragraphs else head
    out = []
    for category, letter in (("commonly consumed food commodities", "(a)"), ("edible fats and oils", "(c)")):
        text = next((p for p in paragraphs if p.startswith(letter)), "")
        out.append(UsSection(number="180.950", substance=category, kind="exemption", heading=head,
                             exemption=UsExemption(text=f"{intro} {text}"[:EXEMPTION_TEXT_CHARS])))
    for table in div.iter("TABLE"):
        header, rows = _table_rows(table)
        if not header or not header[0].startswith("chemical"):
            continue
        for r in rows:
            if r and r[0]:
                out.append(UsSection(number="180.950", substance=r[0], kind="exemption", heading=head,
                                     exemption=UsExemption(text=f"{intro} (e) {r[0]}"[:EXEMPTION_TEXT_CHARS])))
    return out


def parse_section(div: ET.Element) -> UsSection | None:
    number = div.get("N") or ""
    head = _text(div.find("HEAD"))
    found = substance_of(head)
    if _skipped(number) or found is None:
        return None
    substance, kind = found
    section = UsSection(number=number, substance=substance, kind=kind, heading=head)
    paragraph, sub = "a", None
    first_text = None
    for el in div.iter():
        if el.tag == "P":
            raw = ET.tostring(el, encoding="unicode")
            text = _text(el)
            first_text = first_text or text
            inner = re.sub(r"^<P[^>]*>", "", raw)
            if m := _PARAGRAPH.match(text):
                paragraph, sub = m.group(1), None
            if m := _SUBPARAGRAPH.match(inner):
                sub = m.group(1)
        elif el.tag == "TABLE" and kind == "tolerance":
            header, rows = _table_rows(el)
            if not header or "commodit" not in header[0]:
                continue
            ppm = next((i for i, h in enumerate(header) if "part" in h and "million" in h), None)
            expiry = next((i for i, h in enumerate(header) if "expir" in h or "revoc" in h), None)
            if ppm is None:
                continue
            for r in rows:
                if len(r) <= ppm or not r[0]:
                    continue
                section.tolerances.append(UsTolerance(
                    commodity=r[0], value_ppm=parse_ppm(r[ppm]), value_text=r[ppm],
                    expires_on=_to_date(r[expiry]) if expiry is not None and len(r) > expiry else None,
                    paragraph=f"({paragraph})" + (f"({sub})" if sub else ""), kind=PARAGRAPH_KIND[paragraph]))
    if kind == "exemption":
        # the whole section: conditions often come after paragraph (a) (copper: (b) fungicides on growing crops)
        full = " ".join(_text(p) for p in div.iter("P")) or first_text or head
        section.exemption = UsExemption(text=full[:EXEMPTION_TEXT_CHARS])
    return section


SPECIAL = {"180.905": parse_180_905, "180.950": parse_180_950}


def parse_part(path: Path) -> list[UsSection]:
    root = ET.parse(path).getroot()
    out: list[UsSection] = []
    for div in root.iter("DIV8"):
        number = div.get("N") or ""
        if number in SPECIAL:
            out += SPECIAL[number](div)
        elif (s := parse_section(div)) is not None:
            out.append(s)
    return out
