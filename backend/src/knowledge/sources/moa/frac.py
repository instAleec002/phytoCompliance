"""FRAC Code List (PDF): a seven-column table, MOA | target site | group name | chemical group | common name | comments
| FRAC code. A row with an empty code continues the group above it, also across pages.

The common-name cell lists one name per line. "(=kiralaxyl)" is a synonym of the name above. A cell describing a
biological agent or an extract ("B. amyloliquefaciens / strain QST713 / ...") is kept as one entry.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from .models import MoaEntry, normalize_code

_SYNONYM = re.compile(r"^\(=\s*([^)]+)\)$")
_ONE_WORD_PARENS = re.compile(r"^\(([\w-]+)\)$")
_COUNTER_IONS = {"pelargonate", "acetate", "chloride", "hydroxide", "hydrochloride", "sulphate", "sulfate"}
_DESCRIPTION = re.compile(r"strain|extract|\(mixtures\)|isolate|cell walls|material of|peptide", re.IGNORECASE)


def names_in_cell(cell: str) -> list[str]:
    lines = [" ".join(line.split()) for line in (cell or "").split("\n") if line.strip()]
    if not lines:
        return []
    if _DESCRIPTION.search(" ".join(lines)) or any(line.endswith((",", ":")) for line in lines[:-1]):
        return [" ".join(lines)]
    lines = _join_counter_ions(lines)
    out: list[str] = []
    for line in lines:
        if m := _SYNONYM.match(line):
            out.append(m.group(1).strip())
        elif m := _ONE_WORD_PARENS.match(line):
            if out and line.lower() != "(bactericide)":
                out.append(m.group(1))            # "(pimaricin)" under natamycin: another name for it
        elif line.startswith("("):
            continue                              # a comment such as "(different salts)"
        else:
            out.append(line)
    return out


def _join_counter_ions(lines: list[str]) -> list[str]:
    """A salt printed over two lines ("choline / pelargonate") is one substance."""
    out: list[str] = []
    for line in lines:
        if out and line.lower() in _COUNTER_IONS and " " not in out[-1]:
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def parse_rows(tables: list[list[list[str | None]]]) -> list[MoaEntry]:
    entries: list[MoaEntry] = []
    code = group_name = None
    for table in tables:
        if not table or len(table[0]) != 7 or "MOA" not in (table[0][0] or ""):
            continue
        for row in table[3:]:
            if (row[6] or "").strip():
                code = normalize_code(row[6])
                group_name = " ".join((row[2] or "").split()) or group_name
            if code is None:
                continue
            for name in names_in_cell(row[4] or ""):
                entries.append(MoaEntry(scheme="FRAC", code=code, name=name, group_name=group_name))
    return entries


def parse_frac(path: Path) -> list[MoaEntry]:
    with pdfplumber.open(path) as pdf:
        tables = [t for page in pdf.pages for t in page.extract_tables()]
    return parse_rows(tables)
