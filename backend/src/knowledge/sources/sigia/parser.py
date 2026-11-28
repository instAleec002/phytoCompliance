"""Turns the positional rows of SIGIA into typed records."""
from __future__ import annotations

import re

from .fields import CROP_FIELDS, PEST_FIELDS, PRODUCT_FIELDS
from .models import Crop, DoseRange, Pest, Product

_SPACES = re.compile(r"\s+")
_NUMBER = re.compile(r"[-+]?\d*\.?\d+")
# a comma separates ingredients unless it sits between two digits, as in the locants of "1,8 CINEOL" or "2,4-D"
_INGREDIENT_SPLIT = re.compile(r"(?<!\d),|,(?!\d)")
# SENASA writes "no interval applies" in the notes in many ways: "UAC / LMR = NO APLICA", "PC y LMR=NA",
# "No aplica PC ni LMR", "P.C: N.A"; "UAC NO DETERMINADO" is not one of them
_INTERVAL = re.compile(r"\b(?:P\.?\s?C|UAC)\b", re.IGNORECASE)
_NOT_APPLICABLE = re.compile(r"\bno\s+aplica\w*|\bN\.?\s?A\b\.?", re.IGNORECASE)


def clean(value) -> str:
    """Trim and collapse inner spaces ("Botrytis  cinerea " -> "Botrytis cinerea")."""
    return _SPACES.sub(" ", str(value if value is not None else "")).strip()


def optional(value) -> str | None:
    text = clean(value)
    return text or None


def to_float(value) -> float | None:
    text = clean(value).replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value) -> int | None:
    number = to_float(value)
    return int(number) if number is not None else None


def dose_range(value) -> DoseRange | None:
    """Doses come as "1.5", "1 - 1.5", ".75 - 1" or "- .7"; the raw text is always kept."""
    raw = clean(value)
    if not raw:
        return None
    numbers = [float(n) for n in _NUMBER.findall(raw.replace(" - ", " ").replace("-", " "))]
    if not numbers:
        return DoseRange(raw=raw, minimum=None, maximum=None)
    return DoseRange(raw=raw, minimum=min(numbers), maximum=max(numbers))


def ingredients(value) -> list[str]:
    seen, out = set(), []
    for part in _INGREDIENT_SPLIT.split(clean(value)):
        name = clean(part)
        if name and name.upper() not in seen:
            seen.add(name.upper())
            out.append(name)
    return out


def interval_not_applicable(interval, notes) -> bool:
    """Blank interval and a note saying that the pre-harvest interval (PC or UAC) does not apply."""
    text = clean(notes)
    return to_int(interval) is None and bool(_INTERVAL.search(text)) and bool(_NOT_APPLICABLE.search(text))


def _as_dict(row: list, fields: list[str]) -> dict:
    if len(row) != len(fields):
        raise ValueError(f"SIGIA row with {len(row)} fields, expected {len(fields)}")
    return dict(zip(fields, row))


def parse_crops(rows: list[list]) -> list[Crop]:
    out = []
    for row in rows:
        r = _as_dict(row, CROP_FIELDS)
        out.append(Crop(crop_id=clean(r["cultivoid"]), scientific_name=clean(r["cultivonombrecientifico"]),
                        common_name=clean(r["cultivonombrecomun"])))
    return out


def parse_pests(rows: list[list]) -> list[Pest]:
    out = []
    for row in rows:
        r = _as_dict(row, PEST_FIELDS)
        out.append(Pest(pest_id=optional(r["plagaid"]), scientific_name=clean(r["plaganombrecientifico"]),
                        common_name=clean(r["plaganombrecomun"]), other_use_class=optional(r["idclaseotrouso"])))
    return out


def parse_products(rows: list[list]) -> list[Product]:
    out = []
    for row in rows:
        r = _as_dict(row, PRODUCT_FIELDS)
        out.append(Product(
            product_id=clean(r["productoid"]),
            trade_name=clean(r["nombrecomercial"]),
            holder_id=clean(r["empresaid"]),
            holder_name=clean(r["razonsocial"]),
            registration_number=clean(r["numeroregistro"]),
            active_ingredients=ingredients(r["principiosactivos"] or r["ingredienteactivo"]),
            use_class=clean(r["clase"]),
            toxicity=optional(r["categoriatoxicologico"]),
            crop_id=clean(r["cultivoid"]),
            pest_id=clean(r["plagaid"]),
            crop_scientific_name=clean(r["cultivonombrecientifico"]),
            pest_scientific_name=clean(r["plaganombrecientifico"]),
            crop_common_name=clean(r["cultivonombrecomun"]),
            pest_common_name=clean(r["plaganombrecomun"]),
            dose_unit=optional(r["unidadmedida"]),
            dose_per_hectare=dose_range(r["dosishectarea"]),
            dose_percent=dose_range(r["dosisporcentaje"]),
            tank_capacity_l=to_float(r["capacidadcilindro"]),
            dose_per_tank=dose_range(r["dosiscilindro"]),
            peru_mrl_mg_kg=to_float(r["limitemaximoresiduo"]),
            preharvest_interval_days=to_int(r["periodocarenciadias"]),
            preharvest_interval_not_applicable=interval_not_applicable(r["periodocarenciadias"], r["observacion"]),
            notes=optional(r["observacion"]),
            product_type=clean(r["tipoproducto"]).upper(),
        ))
    return out
