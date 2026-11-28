"""SIGIA parser on the real answer for blueberry x Botrytis cinerea (24/09/2026) and the blueberry pest list."""
import json
from pathlib import Path

import pytest

from knowledge.sources.sigia.parser import dose_range, ingredients, interval_not_applicable, parse_pests, parse_products

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "sigia"


@pytest.fixture(scope="module")
def products():
    return parse_products(json.loads((FIXTURES / "products_023075_000626.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def pests():
    return parse_pests(json.loads((FIXTURES / "pests_023075.json").read_text(encoding="utf-8")))


def test_counts_match_the_registry(products):
    assert len(products) == 249
    assert sum(p.is_biological for p in products) == 118
    assert sum(not p.is_biological for p in products) == 131


def test_chemical_ingredients_are_few(products):
    chemical = {i.upper() for p in products if not p.is_biological for i in p.active_ingredients}
    assert 25 <= len(chemical) <= 40  # 29 counted by hand on 05/10/2026, mixtures included


def test_names_are_cleaned(products):
    p = products[0]
    assert p.crop_scientific_name == "Vaccinium corymbosum"
    assert p.pest_scientific_name == "Botrytis cinerea"
    assert p.trade_name == "BASUMEX S"


def test_mrl_and_preharvest_interval_are_parsed(products):
    adiko = next(p for p in products if p.trade_name == "ADIKO SC")
    assert adiko.registration_number == "PQUA N° 4333-SENASA"
    assert adiko.active_ingredients == ["PYRACLOSTROBIN", "EXTRACTO DE RHEUM OFFICINALE"]
    assert adiko.peru_mrl_mg_kg == 4.0
    assert adiko.preharvest_interval_days == 14
    assert adiko.tank_capacity_l == 200.0
    assert adiko.dose_per_tank.minimum == 0.75 and adiko.dose_per_tank.maximum == 1.0


def test_missing_values_are_none_not_zero(products):
    basumex = products[0]
    assert basumex.peru_mrl_mg_kg is None
    assert basumex.preharvest_interval_days is None


def test_pests_and_other_uses_are_separated(pests):
    assert any(p.pest_id == "000626" for p in pests)  # Botrytis cinerea
    others = [p for p in pests if p.is_other_use]
    assert others and all(p.other_use_class for p in others)
    assert all(p.pest_id for p in pests if not p.is_other_use)


@pytest.mark.parametrize("raw,low,high", [("1.5", 1.5, 1.5), ("1 - 1.5", 1.0, 1.5), (".75 - 1", 0.75, 1.0), ("- .7", 0.7, 0.7)])
def test_dose_ranges(raw, low, high):
    d = dose_range(raw)
    assert (d.minimum, d.maximum, d.raw) == (low, high, raw)


def test_dose_range_empty():
    assert dose_range("") is None


def test_ingredients_deduplicate():
    assert ingredients("BACILLUS SUBTILIS, BACILLUS SUBTILIS, BREVIBACILLUS BREVIS") == ["BACILLUS SUBTILIS", "BREVIBACILLUS BREVIS"]


def test_wrong_row_length_fails_loudly():
    with pytest.raises(ValueError):
        parse_products([["only", "three", "fields"]])


def test_commas_between_digits_are_locants_not_separators():
    assert ingredients("1,8 CINEOL") == ["1,8 CINEOL"]
    assert ingredients("2,4-D, PICLORAM") == ["2,4-D", "PICLORAM"]
    assert ingredients("FLUDIOXONIL,CYPRODINIL") == ["FLUDIOXONIL", "CYPRODINIL"]


@pytest.mark.parametrize("interval, notes, expected", [
    ("", "UAC / LMR = NO APLICA", True),
    ("", "PC y LMR=NA", True),
    ("", "15 UNIDADES/HA. No aplica PC ni LMR.", True),
    ("", "P.C: N.A      LMR: N.A", True),
    ("", "LMR y PC no aplica (N.A)", True),
    ("", "UAC: NO APLICA, LMR: NO REQUIERE", True),
    ("", "UAC NO DETERMINADO", False),
    ("", "LMR: No aplica", False),
    ("", "", False),
    ("7", "PC: 7 días; LMR: N.A", False),
])
def test_interval_not_applicable_from_the_notes(interval, notes, expected):
    assert interval_not_applicable(interval, notes) is expected
