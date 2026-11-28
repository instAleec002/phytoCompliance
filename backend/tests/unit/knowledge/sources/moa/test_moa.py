"""Mode-of-action parsers, with table rows as pdfplumber and openpyxl return them from the real files of 28/10/2026
(FRAC Code List 2026, IRAC v11.5, HRAC 2026)."""
import httpx
import pytest

from knowledge.normalization.moa import MoaAliases, MoaIndex
from knowledge.sources.moa.client import IncompleteDownload, MoaClient, check_complete
from knowledge.sources.moa.frac import names_in_cell
from knowledge.sources.moa.frac import parse_rows as frac_rows
from knowledge.sources.moa.hrac import parse_rows as hrac_rows
from knowledge.sources.moa.irac import parse_rows as irac_rows
from knowledge.sources.moa.models import MoaEntry, normalize_code
from knowledge.sources.moa.snapshot import LayoutChanged, check_entries

FRAC_HEADER = [["MOA", "TARGET SITE\nAND CODE", "GROUP NAME", "CHEMICAL OR\nBIOLOGICAL GROUP", "(ISO)\nCOMMON NAME",
                "COMMENTS", "FRAC"], [""] * 6 + ["GROUP"], [""] * 6 + ["CODE"]]


def test_codes_are_normalized():
    assert [normalize_code(c) for c in ("M 01", "BM 02", " 11 ", "P 07", "4A", "UNF")] == \
           ["M01", "BM02", "11", "P07", "4A", "UNF"]


@pytest.mark.parametrize("cell, names", [
    ("benalaxyl\nbenalaxyl-M\n(=kiralaxyl)\nfuralaxyl", ["benalaxyl", "benalaxyl-M", "kiralaxyl", "furalaxyl"]),
    ("copper\n(different salts)", ["copper"]),
    ("natamycin\n(pimaricin)", ["natamycin", "pimaricin"]),
    ("tecloftalam\n(Bactericide)", ["tecloftalam"]),
    ("B. amyloliquefaciens\nstrain QST713\nstrain FZB24", ["B. amyloliquefaciens strain QST713 strain FZB24"]),
    ("plant oils\n(mixtures):\neugenol, geraniol,\nthymol", ["plant oils (mixtures): eugenol, geraniol, thymol"]),
    ("choline\npelargonate", ["choline pelargonate"]),
    ("fluopicolide\nfluopimomide", ["fluopicolide", "fluopimomide"]),
])
def test_frac_names_in_a_cell(cell, names):
    assert names_in_cell(cell) == names


def test_frac_rows_carry_the_code_down_and_across_pages():
    page4 = FRAC_HEADER + [["disc", "A1", "PA-fungicides", "acylalanines", "metalaxyl\nmetalaxyl-M", "", "4"],
                           ["", "", "", "oxazolidinones", "oxadixyl", "", ""]]
    page5 = FRAC_HEADER + [["", "", "", "butyrolactones", "ofurace", "", ""],
                           ["", "", "", "", "copper\n(different salts)", "", "M 01"]]
    got = [(e.name, e.code) for e in frac_rows([page4, page5, [["unrelated"]]])]
    assert got == [("metalaxyl", "4"), ("metalaxyl-M", "4"), ("oxadixyl", "4"), ("ofurace", "4"), ("copper", "M01")]


def test_irac_pairs_and_merged_cells():
    table = [["Active Ingredient", "", "MOA", ""], [None, None, "No.", None],
             ["Bistrifluron", "15", None, None],                         # the plain text layout shows 3A here
             ["Ethiofencarb\nEthion", "1A\n1B", None, None],
             ["Bioallethrin S-cyclopentenyl\nisomer", "3A", None, None],
             ["Abamectin", "6", "Azamethiphos", "1B"]]
    got = [(e.name, e.code) for e in irac_rows([table])]
    assert got == [("Bistrifluron", "15"), ("Ethiofencarb", "1A"), ("Ethion", "1B"),
                   ("Bioallethrin S-cyclopentenyl isomer", "3A"), ("Abamectin", "6"), ("Azamethiphos", "1B")]


def test_hrac_rows_and_dual_modes():
    rows = [("MODE OF ACTION", "CHEMICAL CLASSIFICATION", "ACTIVE", "HRAC GLOBAL", "LEGACY HRAC GLOBAL"),
            ("Auxin Mimics", "Phenoxycarboxylates", "2,4-D", 4, "O"),
            ("Mixed", "x", "Active X", "12/32", "F"), ("Unknown", "y", None, None, None)]
    assert [(e.name, e.code) for e in hrac_rows(rows)] == [("2,4-D", "4"), ("Active X", "12"), ("Active X", "32")]
    with pytest.raises(ValueError):
        hrac_rows([("ACTIVE", "CODE")])


def test_layout_check_needs_anchors_and_a_minimum():
    with pytest.raises(LayoutChanged):
        check_entries("HRAC", [MoaEntry(scheme="HRAC", code="9", name="Glyphosate")])


def test_incomplete_downloads_are_rejected():
    check_complete(b"%PDF-1.7 ... %%EOF\n", "pdf")
    with pytest.raises(IncompleteDownload):
        check_complete(b"%PDF-1.7 ... cut", "pdf")
    with pytest.raises(IncompleteDownload):
        check_complete(b"PK\x03\x04 cut", "xlsx")


def test_client_retries_until_the_file_is_complete():
    answers = iter([b"%PDF-1.7 cut", b"%PDF-1.7 whole %%EOF"])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=next(answers)))
    with MoaClient(transport=transport, pause_s=0) as client:
        assert client.download("https://example.org/f.pdf", "pdf").endswith(b"%%EOF")


def test_client_gives_up_loudly():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF cut"))
    with MoaClient(transport=transport, retries=2, pause_s=0) as client, pytest.raises(IncompleteDownload):
        client.download("https://example.org/f.pdf", "pdf")


def test_index_groups_aliases_and_reasons():
    entries = [MoaEntry(scheme="FRAC", code="M01", name="copper"), MoaEntry(scheme="FRAC", code="M02", name="sulphur"),
               MoaEntry(scheme="IRAC", code="UN", name="Sulphur"), MoaEntry(scheme="FRAC", code="P07", name="fosetyl-Al")]
    index = MoaIndex(entries, MoaAliases.load())
    assert index.groups("AZUFRE") == {"FRAC:M02", "IRAC:UN"}
    assert index.groups("OXICLORURO DE COBRE") == {"FRAC:M01"}
    assert index.groups("fosetyl-aluminium") == {"FRAC:P07"}
    assert "regulador" in index.reason("paclobutrazol")
    assert "copper" not in index.missing_targets()
