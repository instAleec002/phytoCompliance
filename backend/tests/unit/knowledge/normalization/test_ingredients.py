"""Ingredient normalization with real SIGIA names and real EU residue names (catalog subset of 27/10/2026)."""
import pytest

from knowledge.normalization.ingredients import Aliases, ResidueIndex, ingredient_key, residue_head

CATALOG = [
    {"pesticide_residue_id": 1, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Pyraclostrobin (F)"},
    {"pesticide_residue_id": 1, "pesticide_residue_lg": "ES", "pesticide_residue_name": "Piraclostrobina (F)"},
    {"pesticide_residue_id": 2, "pesticide_residue_lg": "EN",
     "pesticide_residue_name": "Emamectin B1a and its salts, expressed as emamectin B1a (free base)(R)"},
    {"pesticide_residue_id": 3, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Total copper"},
    {"pesticide_residue_id": 4, "pesticide_residue_lg": "EN",
     "pesticide_residue_name": "Spirotetramat and spirotetramat-enol (sum of), expressed as spirotetramat"},
    {"pesticide_residue_id": 5, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Sulphur"},
    {"pesticide_residue_id": 6, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Flumioxazine"},
    {"pesticide_residue_id": 7, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Paraffin oil (CAS 64742-46-7)"},
    {"pesticide_residue_id": 8, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Paraffin oil (CAS 8042-47-5)"},
]


@pytest.fixture(scope="module")
def index():
    return ResidueIndex(CATALOG, Aliases.load())


@pytest.mark.parametrize("raw,key", [
    ("Pyraclostrobin (F)", "pyraclostrobin"),
    ("Bifenthrin (sum of isomers)(F)", "bifenthrin"),
    ("Fatty acids:  Octanoic acid (+)(++)", "fatty acids: octanoic acid"),
    ("COPPER SULFATE PENTAHYDRATE", "copper sulphate pentahydrate"),
    ("ÓXIDO CUPROSO", "oxido cuproso"),
])
def test_ingredient_key(raw, key):
    assert ingredient_key(raw) == key


def test_residue_head():
    assert residue_head("spirotetramat and spirotetramat-enol") == "spirotetramat"
    assert residue_head("formetanate: sum of formetanate and its salts") == "formetanate"
    assert residue_head("cyanamide including salts") == "cyanamide"
    assert residue_head("1,4-dimethylnaphthalene") == "1,4-dimethylnaphthalene"   # locant, not a separator
    assert residue_head("2,4-d, sum of 2,4-d and its esters") == "2,4-d"


@pytest.mark.parametrize("sigia,residue", [
    ("PYRACLOSTROBIN", 1),          # same ISO name, EU footnote removed
    ("EMAMECTIN BENZOATO", 2),      # Spanish salt name -> EU residue for the active part
    ("COPPER HYDROXIDE", 3),        # every copper salt -> total copper
    ("OXICLORURO DE COBRE", 3),
    ("SPIROTETRAMAT", 4),           # leading name of the EU definition
    ("AZUFRE", 5),                  # Spanish name
    ("FLUMIOXAZIN", 6),             # ISO spelling vs EU spelling
])
def test_sigia_names_meet_eu_residues(index, sigia, residue):
    match = index.match(sigia)
    assert match.residue_ids == [residue] and not match.ambiguous


def test_mineral_oil_is_ambiguous_not_guessed(index):
    match = index.match("ACEITE MINERAL")
    assert match.residue_ids == [7, 8] and match.ambiguous


def test_known_absence_carries_its_reason(index):
    match = index.match("TOLFENPYRAD")
    assert not match.matched and match.not_in_eu


def test_unknown_ingredient_is_not_invented(index):
    match = index.match("SUSTANCIA INEXISTENTE")
    assert not match.matched and match.not_in_eu is None


BIO_CATALOG = [
    {"pesticide_residue_id": 10, "pesticide_residue_lg": "EN",
     "pesticide_residue_name": "Bacillus amyloliquefaciens (formerly subtilis) str. QST 713"},
    {"pesticide_residue_id": 11, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Bacillus subtilis strain IAB/BS03"},
    {"pesticide_residue_id": 12, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Potassium hydrogen carbonate"},
    {"pesticide_residue_id": 13, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Azadirachtin"},
    {"pesticide_residue_id": 14, "pesticide_residue_lg": "EN", "pesticide_residue_name": "Total copper"},
]


@pytest.fixture(scope="module")
def bio_index():
    return ResidueIndex(BIO_CATALOG, Aliases.load())


def test_species_without_strain_maps_to_every_listed_strain(bio_index):
    m = bio_index.match("BACILLUS SUBTILIS")
    assert m.residue_ids == [10, 11] and m.ambiguous      # the domain then uses the strictest and says so


@pytest.mark.parametrize("sigia,residue", [
    ("BICARBONATO DE POTASIO", 12), ("EXTRACTO DE NEEM", 13), ("AZADIRACHTA", 13), ("SULFATO DE COBRE", 14),
])
def test_biological_products_spanish_names(bio_index, sigia, residue):
    assert bio_index.match(sigia).residue_ids == [residue]


def test_biological_absence_has_a_reason(bio_index):
    m = bio_index.match("BACILLUS THURINGIENSIS VAR. KURSTAKI")
    assert not m.matched and "Bacillus thuringiensis" in m.not_in_eu
    assert "nutriente" in bio_index.match("AMINOACIDOS").not_in_eu


def test_alias_targets_are_checked_against_the_catalog(bio_index):
    missing = bio_index.missing_targets()
    assert "total copper" not in missing and "azadirachtin" not in missing
    assert "plant oils / clove oil eugenol" in missing                  # not in this small catalog


def test_an_alias_cannot_be_both_mapped_and_absent(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("to_residue:\n  x: y\nnot_in_eu:\n  x: motivo\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Aliases.load(f)
