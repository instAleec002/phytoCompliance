"""Building graph records: version identity, the REPLACES chain with valid_until, ties, end dates never invented,
one edge per (type, source, target) and the consistency check against the EU status."""
from datetime import date

from knowledge.graph.consistency import check_against_eu_status
from knowledge.graph.records import GraphRecords, _add_mrl_versions, version_key
from knowledge.sources.eu_mrl.parser import parse_mrl


def row(residue, applies, regulation, status="No longer applicable", annex="Annex II", value="4", voted=None, nxt=None):
    return parse_mrl({"pesticide_residue_id": residue, "product_id": 46, "mrl_value": value, "applicability_text": status,
                      "application_date": applies, "regulation_number": regulation, "included_in_annex": annex,
                      "voted_date": voted, "next_pesticide_residue_id": nxt})


def build(rows):
    rec = GraphRecords()
    _add_mrl_versions(rec, rows, "blueberry", {}, "eu_mrl:test")
    return rec


def test_versions_of_one_residue_form_a_chain_with_valid_until():
    rows = [row(1, "01/09/2008", "Reg A", value="0.5"), row(1, "06/04/2013", "Reg B"),
            row(1, "11/02/2026", "Reg C", status="Applicable")]
    rec = build(rows)
    mv = rec.nodes["MrlVersion"]
    a, b, c = (version_key(r) for r in rows)
    assert mv[a]["valid_until"] == date(2013, 4, 6) and mv[b]["valid_until"] == date(2026, 2, 11)
    assert "valid_until" not in mv[c]
    assert {(e["from"], e["to"]) for e in rec.edges["REPLACES"]} == {(b, a), (c, b)}


def test_same_limit_in_two_annexes_does_not_replace_itself():
    rows = [row(2, "05/12/2024", "Reg X", status="Applicable", annex="Annex II"),
            row(2, "05/12/2024", "Reg X", status="Applicable", annex="Annex III")]
    rec = build(rows)
    assert not rec.edges.get("REPLACES")


def test_same_date_later_vote_replaces_the_earlier_regulation():
    # Terbuthylazine, 27/10/2026: Reg. 2021/618 and Reg. 2021/1795 both apply from 06/11/2021
    old = row(385, "06/11/2021", "Reg. (EU) 2021/618", voted="01/04/2021", value="0.01*")
    new = row(385, "06/11/2021", "Reg. (EU) 2021/1795", status="Applicable", voted="01/10/2021", value="0.01*")
    rec = build([old, new])
    assert rec.nodes["MrlVersion"][version_key(old)]["valid_until"] == date(2021, 11, 6)
    assert check_against_eu_status(rec, date(2026, 10, 27))["blueberry"]["only_by_dates"] == []


def test_new_residue_definition_replaces_the_old_one():
    old = row(213, "01/09/2008", "Reg A", value="0.05*", nxt=3710)
    new = row(3710, "29/01/2027", "Reg. (EU) No. 2026/1546", status="Not yet applicable", value="0.01*")
    rec = build([old, new])
    assert rec.nodes["MrlVersion"][version_key(old)]["valid_until"] == date(2027, 1, 29)


def test_end_date_is_flagged_not_invented():
    withdrawn = row(73, "01/09/2008", "Reg A", value="0.01*")
    rec = build([withdrawn])
    node = rec.nodes["MrlVersion"][version_key(withdrawn)]
    assert node["end_date_unknown"] is True and "valid_until" not in node


def test_consistency_matches_eu_status():
    rows = [row(1, "01/09/2008", "Reg A"), row(1, "11/02/2026", "Reg C", status="Applicable"),
            row(9, "29/01/2027", "Reg F", status="Not yet applicable")]
    report = check_against_eu_status(build(rows), date(2026, 10, 27))["blueberry"]
    assert report["in_force_by_dates"] == report["applicable_by_eu"] == 1
    assert report["only_by_dates"] == report["only_by_eu"] == []


def test_edges_are_unique_per_type_source_and_target():
    rec = GraphRecords()
    for _ in range(34):  # pyraclostrobin is in 34 products, but it is measured as its residue once
        rec.edge("MEASURED_AS", "pyraclostrobin", "EU:1")
    assert len(rec.edges["MEASURED_AS"]) == 1
