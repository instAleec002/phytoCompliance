"""40 CFR Part 180: parser, commodity rules and normalization, with fragments of the eCFR XML of 26/10/2026."""
import xml.etree.ElementTree as ET

import pytest

from knowledge.normalization.us import UsAliases, UsIndex
from knowledge.sources.us_tolerances.client import IncompleteDownload, check_complete
from knowledge.sources.us_tolerances.commodities import load_rules, normalize
from knowledge.sources.us_tolerances.parser import parse_180_905, parse_ppm, parse_section, substance_of

PYRACLOSTROBIN = """<DIV8 N="180.582" TYPE="SECTION"><HEAD>&#xA7; 180.582 Pyraclostrobin; tolerances for residues.</HEAD>
<P>(a) <I>General.</I> (1) Tolerances are established for residues of the fungicide pyraclostrobin.</P>
<TABLE><THEAD><TR><TH>Commodity</TH><TH>Parts per million</TH></TR></THEAD><TBODY>
<TR><TD>Avocado</TD><TD>0.6</TD></TR>
<TR><TD>Bushberry subgroup 13-07B</TD><TD>4.0</TD></TR>
<TR><TD>Grape<SU>1</SU></TD><TD>2.0</TD></TR></TBODY></TABLE>
<P>(b) <I>Section 18 emergency exemptions.</I> Time-limited tolerances are established.</P>
<TABLE><THEAD><TR><TH>Commodity</TH><TH>Parts per million</TH><TH>Expiration/revocation date</TH></TR></THEAD>
<TBODY><TR><TD>Blueberry</TD><TD>1.5</TD><TD>12/31/2027</TD></TR></TBODY></TABLE>
<P>(c) <I>Tolerances with regional registrations.</I> [Reserved]</P></DIV8>"""

COPPER = """<DIV8 N="180.1021" TYPE="SECTION"><HEAD>&#xA7; 180.1021 Copper; exemption from the requirement of a
tolerance.</HEAD><P>(a) Copper is exempted in cattle, meat ... when it results from algicide uses.</P>
<P>(b) The following copper compounds are exempt when applied as a fungicide to growing crops.</P></DIV8>"""

PETROLEUM = """<DIV8 N="180.905" TYPE="SECTION"><HEAD>&#xA7; 180.905 Pesticide chemicals; exemptions from the
requirement of a tolerance.</HEAD><P>(a) When applied to growing crops, the following are exempt:</P>
<P>(1) Petroleum oils.</P><P>(2) Piperonyl butoxide.</P><P>(3) Pyrethrins.</P>
<P>(c) Not exempted when applied at the time of or after harvest.</P></DIV8>"""


def test_substance_and_kind_from_the_heading():
    assert substance_of("§ 180.582 Pyraclostrobin; tolerances for residues.") == ("Pyraclostrobin", "tolerance")
    assert substance_of("§ 180.1011 Viable spores of the microorganism Bacillus thuringiensis Berliner; exemption "
                        "from the requirement of a tolerance.")[1] == "exemption"
    assert substance_of("§ 180.41 Crop group tables.") is None


def test_tolerances_with_paragraph_footnotes_and_expiry():
    s = parse_section(ET.fromstring(PYRACLOSTROBIN))
    rows = [(t.commodity, t.value_ppm, t.paragraph, t.kind, t.expires_on) for t in s.tolerances]
    assert rows[1] == ("Bushberry subgroup 13-07B", 4.0, "(a)(1)", "general", None)
    assert rows[2][0] == "Grape"                                         # footnote mark dropped
    assert rows[3][2:4] == ("(b)", "section_18") and str(rows[3][4]) == "2027-12-31"


def test_exemption_keeps_every_condition():
    s = parse_section(ET.fromstring(COPPER))
    assert s.kind == "exemption" and "(b)" in s.exemption.text and "fungicide to growing crops" in s.exemption.text


def test_180_905_lists_each_exempt_chemical():
    got = parse_180_905(ET.fromstring(PETROLEUM))
    assert [s.substance for s in got] == ["Petroleum oils", "Piperonyl butoxide", "Pyrethrins"]
    assert "after harvest" in got[0].exemption.text


def test_definitions_and_crop_groups_are_skipped():
    div = ET.fromstring('<DIV8 N="180.41"><HEAD>§ 180.41 Crop group tables; tolerances.</HEAD></DIV8>')
    assert parse_section(div) is None


@pytest.mark.parametrize("text, value", [("4.0", 4.0), ("0.1(N)", 0.1), ("4.0 1", 4.0), ("1 7.0", 7.0),
                                         ("0.01 ppm", 0.01), (".5", 0.5), ("6. 0", 6.0), ("*", None), ("", None)])
def test_ppm_values(text, value):
    assert parse_ppm(text) == value


@pytest.fixture(scope="module")
def rules():
    return load_rules()


@pytest.mark.parametrize("crop, commodity, covered", [
    ("blueberry", "Bushberry subgroup 13-07B", True),
    ("blueberry", "Bushberrry subgroup 13-07B", True),
    ("blueberry", "Bushberry subgroup 13-07B, except lowbush blueberry", True),
    ("blueberry", "Bushberry subgroup 13-07B, except lingonberry and blueberry, lowbush", True),
    ("blueberry", "Berry, low growing, subgroup 13-07G", False),           # lowbush only
    ("blueberry", "Blueberry, lowbush", False),
    ("blueberry", "Berry group 13", True),
    ("table_grape", "Fruit, small, vine climbing, except fuzzy kiwifruit, subgroup 13-07F", True),
    ("table_grape", "Fruit, small, vine climbing, except grape, subgroup 13-07E", False),
    ("table_grape", "Grape, raisin", False),
    ("table_grape", "Grape (import)", True),
    ("avocado", "Tropical and subtropical, medium to large fruit, smooth, inedible peel subgroup 24B, except banana", True),
    ("avocado", "Avocado, imported", True),
])
def test_commodity_rules(rules, crop, commodity, covered):
    assert rules[crop].covers(commodity) is covered


def test_commodity_flags(rules):
    assert "importación" in rules["avocado"].note("Avocado, imported")
    assert normalize("Grape (import)") != normalize("Grape")


def test_index_aliases_biological_prefix_and_reasons():
    from knowledge.sources.us_tolerances.models import UsExemption, UsSection
    sections = [UsSection(number="180.449", substance="Avermectin B1 and its delta-8,9-isomer", kind="tolerance",
                          heading=""),
                UsSection(number="180.1021", substance="Copper", kind="exemption", heading="",
                          exemption=UsExemption(text="")),
                UsSection(number="180.1209", substance="Bacillus subtilis strain QST 713", kind="exemption",
                          heading="", exemption=UsExemption(text=""))]
    index = UsIndex(sections, UsAliases.load())
    assert [s.number for s in index.sections("ABAMECTINA")] == ["180.449"]
    assert [s.number for s in index.sections("OXICLORURO DE COBRE")] == ["180.1021"]
    assert [s.number for s in index.sections("bacillus subtilis", biological=True)] == ["180.1209"]
    assert index.sections("bacillus subtilis") == []                    # the prefix rule is only for biologicals
    assert "40 CFR 180" in index.reason("hymexazol")


def test_incomplete_xml_is_rejected():
    check_complete(b'<ECFR><DIV5 N="180"><DIV8 N="180.1"/></DIV5></ECFR>')
    with pytest.raises(IncompleteDownload):
        check_complete(b'<ECFR><DIV5 N="180"><DIV8 N="180.1"')
    with pytest.raises(IncompleteDownload):
        check_complete(b"<ECFR><DIV5 N='170'/></ECFR>")


def test_heading_with_a_comma_instead_of_the_semicolon():
    assert substance_of("§ 180.503 Cymoxanil, tolerance for residues.") == ("Cymoxanil", "tolerance")
    assert substance_of("§ 180.667 Cyflufenamid, tolerance for residues.") == ("Cyflufenamid", "tolerance")
    assert substance_of("§ 180.950 Tolerance exemptions for minimal risk active and inert ingredients.") is None


@pytest.mark.parametrize("head, expected", [
    ("§ 180.1148 Occlusion Bodies of the Granulosis Virus of Cydia pomenella; tolerance exemption.",
     ("Occlusion Bodies of the Granulosis Virus of Cydia pomenella", "exemption")),
    ("§ 180.1226 Bacillus pumilus strain QST2808; temporary exemption from the requirement of a tolerance.",
     ("Bacillus pumilus strain QST2808", "exemption")),
    ("§ 180.1329 Bacillus subtilis strain IAB/BS03, exemption from the requirement of a tolerance.",
     ("Bacillus subtilis strain IAB/BS03", "exemption")),
    ("§ 180.438 Lambda-cyhalothrin and an isomer gamma-cyhalothrin; tolerances for residues.",
     ("Lambda-cyhalothrin and an isomer gamma-cyhalothrin", "tolerance")),
])
def test_heading_variants(head, expected):
    assert substance_of(head) == expected


def test_heading_without_separator_keeps_the_whole_chemical_name():
    head = ("§ 180.527 Flufenacet, N-(4-fluorophenyl)-N-(1-methylethyl)-2-[[5-(trifluoromethyl)-1, 3, 4-thiadiazol-2-yl] "
            "oxy]acetamide and its metabolites containing the 4-fluoro-N-methylethyl benzenamine tolerances for residues.")
    name, kind = substance_of(head)
    assert kind == "tolerance" and name.startswith("Flufenacet, N-") and name.endswith("benzenamine")


def test_footnote_markers_do_not_hide_a_commodity_but_group_codes_stay():
    from knowledge.sources.us_tolerances.commodities import load_rules, normalize
    rules = load_rules()
    assert normalize("Avocado 1") == "avocado" and normalize("Grape, table 2") == "grape table"
    assert rules["avocado"].covers("Avocado 1") and rules["table_grape"].covers("Grape 3")
    assert normalize("Berry group 13") == "berry group 13"                       # a group code is kept
    assert rules["blueberry"].covers("Berry group 13") and not rules["avocado"].covers("Grape 1")
