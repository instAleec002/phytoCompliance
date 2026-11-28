"""EU active substances (ARfD) and EFSA PRIMo 3.1 rows, with values as served on 28/10/2026."""
import pytest

from knowledge.normalization.substances import SubstanceAliases, SubstanceIndex
from knowledge.sources.eu_substances.parser import parse_arfd, parse_substances
from knowledge.sources.primo.parser import parse_rows


@pytest.mark.parametrize("text, expected", [("0.03 mg/kg bw", (0.03, "set")), ("Not appl.", (None, "not_needed")),
                                            (None, (None, "not_set")), ("", (None, "not_set"))])
def test_arfd_values(text, expected):
    assert parse_arfd(text) == expected


def row(sid, name, arfd, source="EFSA"):
    return {"substance_id": sid, "substance_name": name, "substance_status": "Approved", "tox_value_arfd": arfd,
            "tox_source_earfd": source, "as_micro_org": "No"}


def test_rows_repeated_per_residue_are_merged_and_conflicts_fail():
    rows = [row(1219, "Pyraclostrobin", "0.03 mg/kg bw")] * 3 + [row(838, "Emamectin", "0.01 mg/kg bw")]
    assert [(s.name, s.arfd_mg_kg_bw) for s in parse_substances(rows)] == [("Emamectin", 0.01), ("Pyraclostrobin", 0.03)]
    with pytest.raises(ValueError):
        parse_substances([row(1, "X", "0.1 mg/kg bw"), row(1, "X", "0.2 mg/kg bw")])


def test_ingredient_arfd_through_aliases_and_mixed_entries():
    subs = parse_substances([row(1, "Copper compounds", "Not appl."), row(2, "Emamectin", "0.01 mg/kg bw"),
                             row(3, "Paraffin oil/(CAS 8042-47-5)", "Not appl."),
                             row(4, "Paraffin oil/(CAS 64742-54-7)", None)])
    index = SubstanceIndex(subs, SubstanceAliases.load())
    assert index.arfd("OXICLORURO DE COBRE").status == "not_needed"
    assert index.arfd("EMAMECTIN BENZOATO").value_mg_kg_bw == 0.01
    assert index.arfd("ACEITE MINERAL").status == "not_set"        # some CAS entries say nothing: not assumed
    assert index.arfd("unknown") is None


HEADER = [None] * 10 + [("Level", "Code no.", "Commodity", "Level used", "MRL", "x", "x", "x", "x", "Comment", "GAP",
                         "PHT", "PF", "VF", "Large portion (expressed as g/kg bw)", "Percentile", "MS critical diet",
                         "Body weight \n(kg)", "LP g/person", "Unit weight, \nedible portion \n(g)", "src",
                         "Unit weight RAC", "src", "Case", "Variability \nfactor for IESTI ")]


def test_primo_rows_for_the_crops():
    rows = HEADER + [(4, 154010, "Blueberries", 4, 0, 0, None, 0, None, None, 0, None, None, 0, 5.962, "estimate",
                      "NL child", 18.4, 109.7008, "<25", "NL", "<25", "NL", 1, 1),
                     (4, 110010, "Grapefruits", 4, 0, 0, None, 0, None, None, 0, None, None, 0, 15.7, 90, "DE child",
                      16.15, 253.55, 270.49, "DE", 393.5, "DE", "2b", 5)]
    [c] = parse_rows(rows, "children", {154010})
    assert (c.case, c.unit_below_25g, c.unit_edible_g, c.lp_g_kg_bw) == ("1", True, None, 5.962)


def test_primo_header_change_fails():
    rows = [None] * 10 + [tuple(["x"] * 25)]
    with pytest.raises(ValueError):
        parse_rows(rows, "children", {154010})
