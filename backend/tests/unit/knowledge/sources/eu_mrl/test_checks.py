"""Completeness checks: cut downloads, overlapping pages, unnamed residues and uneven products are caught."""
import json

import pytest

from knowledge.sources.eu_mrl.checks import (
    IncompleteData,
    check_names,
    check_ndjson_complete,
    check_pages,
    check_same_structure,
)


def test_cut_download_is_detected(tmp_path):
    whole = tmp_path / "whole.ndjson"
    whole.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    assert check_ndjson_complete(whole)["last_line_complete"]

    cut = tmp_path / "cut.ndjson"
    cut.write_text('{"a": 1}\n{"mrl_lod":"*","regulation_number":"Reg. (EU) 2019', encoding="utf-8")  # as on 27/10/2026
    with pytest.raises(IncompleteData):
        check_ndjson_complete(cut)


def test_overlapping_pages_are_detected():
    row = {"pesticide_residue_id": 1, "included_in_annex": "Annex III"}
    with pytest.raises(IncompleteData):
        check_pages([row, dict(row)])


def test_same_limit_in_two_annexes_is_not_a_duplicate():
    rows = [{"pesticide_residue_id": 1, "included_in_annex": "Annex III"},
            {"pesticide_residue_id": 1, "included_in_annex": "Annex II"}]
    assert check_pages(rows)["exact_duplicates"] == 0


def test_applicable_residue_without_name_fails():
    items = [{"pesticide_residue_id": 9, "applicability_text": "Applicable"},
             {"pesticide_residue_id": 8, "applicability_text": "No longer applicable"}]
    with pytest.raises(IncompleteData):
        check_names(items, catalog=[{"pesticide_residue_id": 8}])
    assert check_names(items, catalog=[{"pesticide_residue_id": 9}])["named"] == 1


def test_products_must_have_the_same_structure():
    assert check_same_structure({"blueberry": 2402, "avocado": 2402})["versions_per_product"] == 2402
    with pytest.raises(IncompleteData):
        check_same_structure({"blueberry": 2402, "avocado": 309})


def test_real_page_has_no_repeated_rows():
    from pathlib import Path
    page = Path(__file__).resolve().parents[4] / "fixtures" / "eu_mrl" / "mrls_product46_page1.json"
    items = json.loads(page.read_text(encoding="utf-8"))["value"]
    assert check_pages(items)["rows"] == 100
