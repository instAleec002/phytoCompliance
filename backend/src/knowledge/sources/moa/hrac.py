"""HRAC Global Herbicide MoA Classification, Master List (xlsx): MODE OF ACTION | CHEMICAL CLASSIFICATION | ACTIVE |
HRAC GLOBAL | LEGACY HRAC GLOBAL."""
from __future__ import annotations

from pathlib import Path

import openpyxl

from .models import MoaEntry, normalize_code

HEADER = ("MODE OF ACTION", "CHEMICAL CLASSIFICATION", "ACTIVE", "HRAC GLOBAL")


def parse_rows(rows: list[tuple]) -> list[MoaEntry]:
    header = tuple(str(c or "").strip().upper() for c in rows[0][:4])
    if header != HEADER:
        raise ValueError(f"HRAC master list with another header: {header}")
    entries = []
    for row in rows[1:]:
        mode, _, active, code = (row + (None,) * 4)[:4]
        if active is None or code is None or not str(code).strip():
            continue
        for part in str(code).split("/"):          # "12/32": an active with two modes of action
            entries.append(MoaEntry(scheme="HRAC", code=normalize_code(part), name=" ".join(str(active).split()),
                                    group_name=str(mode).strip() if mode else None))
    return entries


def parse_hrac(path: Path) -> list[MoaEntry]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return parse_rows(list(wb["Master List"].iter_rows(values_only=True)))
    finally:
        wb.close()
