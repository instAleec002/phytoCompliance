"""EFSA PRIMo revision 3.1 (xlsm): the consumption data of the acute intake (IESTI) calculation.

The sheets ``acute_overview_children`` and ``acute_overview_adults`` list, per commodity (EU code without the leading
zero: 154010 blueberries), the large portion of the most critical diet, its body weight, the unit weight of the edible
portion ("<25" means case 1), the IESTI case and its variability factor. The workbook is read with its cached values.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from .models import AcuteConsumption

SHEETS = {"children": "acute_overview_children", "adults": "acute_overview_adults"}
HEADER_ROW = 10
COLUMNS = {"code": 1, "commodity": 2, "lp_g_kg_bw": 14, "percentile": 15, "diet": 16, "bw_kg": 17,
           "lp_g_person": 18, "unit_edible_g": 19, "unit_rac_g": 21, "case": 23, "vf": 24}
EXPECTED = {14: "large portion (expressed as g/kg bw)", 17: "body weight", 19: "unit weight", 23: "case",
            24: "variability"}


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_header(row: tuple) -> None:
    for col, text in EXPECTED.items():
        cell = " ".join(str(row[col] or "").lower().split())
        if not cell.startswith(text):
            raise ValueError(f"PRIMo header changed at column {col}: {row[col]!r}")


def parse_rows(rows: list[tuple], population: str, codes: set[int]) -> list[AcuteConsumption]:
    check_header(rows[HEADER_ROW])
    out = []
    for row in rows[HEADER_ROW + 1:]:
        code = row[COLUMNS["code"]] if len(row) > COLUMNS["vf"] else None
        if not isinstance(code, int | float) or int(code) not in codes:
            continue
        unit = row[COLUMNS["unit_edible_g"]]
        out.append(AcuteConsumption(
            commodity_code=int(code), commodity=str(row[COLUMNS["commodity"]]), population=population,
            diet=str(row[COLUMNS["diet"]]), percentile=str(row[COLUMNS["percentile"]]),
            lp_g_kg_bw=float(row[COLUMNS["lp_g_kg_bw"]]), bw_kg=float(row[COLUMNS["bw_kg"]]),
            lp_g_person=float(row[COLUMNS["lp_g_person"]]), unit_edible_g=_number(unit),
            unit_below_25g=str(unit).strip() == "<25", case=str(row[COLUMNS["case"]]).strip(),
            variability_factor=float(row[COLUMNS["vf"]])))
    return out


def parse_primo(path: Path, codes: set[int]) -> list[AcuteConsumption]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [c for population, sheet in SHEETS.items()
                for c in parse_rows(list(wb[sheet].iter_rows(values_only=True)), population, codes)]
    finally:
        wb.close()
