"""Controlled vocabulary: labels from SIGIA and AGROVOC point to graph terms; expansion adds the missing synonyms."""
import json

from knowledge.vocabulary.agrovoc import norm
from knowledge.vocabulary.index import Vocabulary

PESTS = [("001450", "Oidium sp", "Oidiosis"), ("000437", "Erysiphe necator", "Oidiosis"),
         ("010880", "Oligonychus punicae", "Acaro")]


def test_norm_drops_accents_case_and_punctuation():
    assert norm("¿Arándano, en VID?") == "arandano en vid"


def test_one_label_names_several_pests_and_crops_are_found():
    v = Vocabulary.build(None, PESTS, {"pyraclostrobin": "piraclostrobina"})
    keys = {f"{t.kind}:{t.key}" for t in v.find("¿Cómo controlo la oidiosis en vid?")}
    assert {"pest:001450", "pest:000437", "crop:table_grape"} <= keys
    syn = v.expand("¿Cómo controlo la oidiosis en vid?")
    assert "Erysiphe necator" in syn and "uva de mesa" in syn
    assert v.find("dosis de piraclostrobina")[0].key == "pyraclostrobin"


def test_agrovoc_labels_join_the_term(tmp_path):
    (tmp_path / "conceptos.json").write_text(json.dumps({
        "u:1": {"uri": "u:1", "pref": {"es": ["Persea americana"], "en": ["Persea americana"]},
                "alt": {"es": ["aguacatero"]}}}), encoding="utf-8")
    (tmp_path / "enlaces.json").write_text(json.dumps([{"kind": "crop", "key": "avocado", "uri": "u:1"}]), encoding="utf-8")
    v = Vocabulary.build(tmp_path, [], {})
    assert v.terms[("crop", "avocado")].uri == "u:1"
    assert [t.key for t in v.find("plagas del aguacatero")] == ["avocado"]
    assert "palta" in v.expand("plagas del aguacatero")
