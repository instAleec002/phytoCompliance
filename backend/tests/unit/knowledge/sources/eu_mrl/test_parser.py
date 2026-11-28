"""EU Pesticides Database parser on real answers for blueberry (product 46, code 0154010)."""
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from knowledge.sources.eu_mrl.models import Applicability
from knowledge.sources.eu_mrl.parser import iter_ndjson, parse_mrl, parse_page, parse_products, to_float

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "eu_mrl"


@pytest.fixture(scope="module")
def page():
    return parse_page(json.loads((FIXTURES / "mrls_product46_page1.json").read_text(encoding="utf-8")))


def test_page_statuses(page):
    assert len(page) == 100
    assert Counter(m.applicability for m in page) == {
        Applicability.NO_LONGER: 63, Applicability.APPLICABLE: 36, Applicability.NOT_YET: 1}


def test_not_yet_applicable_keeps_its_future_date(page):
    future = next(m for m in page if m.applicability is Applicability.NOT_YET)
    assert future.regulation == "Reg. (EU) No. 2026/1546"
    assert future.voted_on == date(2026, 4, 16)
    assert future.applies_from == date(2027, 1, 29)
    assert future.value_mg_kg == 0.01 and future.at_limit_of_determination
    assert not future.applies_on(date(2026, 12, 31)) and future.applies_on(date(2027, 1, 29))


def test_versions_are_linked(page):
    with_next = [m for m in page if m.next_residue_id]
    assert with_next and all(m.next_residue_id != m.residue_id for m in with_next)


def test_values_and_limit_of_determination():
    assert to_float("0.01*") == 0.01 and to_float("4") == 4.0
    assert to_float("No MRL required") is None and to_float("") is None


def test_exempt_is_not_the_same_as_missing():
    exempt = parse_mrl({"pesticide_residue_id": 1, "product_id": 46, "mrl_value": "No MRL required",
                        "applicability_text": "Applicable"})
    assert exempt.no_mrl_required and exempt.value_mg_kg is None
    default = parse_mrl({"pesticide_residue_id": 2, "product_id": 46, "mrl_value": "0.01*", "mrl_value_only": "0.01",
                         "mrl_lod": "*", "applicability_text": "Applicable"})
    assert not default.no_mrl_required and default.at_limit_of_determination


def test_bulk_rows_carry_names_and_filter_by_code():
    path = FIXTURES / "download_0154010_sample.ndjson"
    rows = list(iter_ndjson(path.open(encoding="utf-8"), product_codes={"0154010"}))
    assert rows and all(r.product_code == "0154010" and r.residue_name for r in rows)
    chlorpyrifos = [r for r in rows if r.residue_name.startswith("Chlorpyrifos  (F)") or r.residue_name == "Chlorpyrifos  (F)"]
    assert any(r.applicability is Applicability.APPLICABLE and r.value_mg_kg == 0.01 for r in chlorpyrifos)
    assert list(iter_ndjson(path.open(encoding="utf-8"), product_codes={"9999999"})) == []


def test_products():
    products = parse_products(json.loads((FIXTURES / "products_page1.json").read_text(encoding="utf-8")))
    assert products and all(p.code and p.name for p in products)
