from evaluation.judgments import Judgments, cohen_kappa, graded_metrics, text_hash

TEXT = "La oidiosis del arándano causada por Erysiphe elevata se desarrolla con humedad relativa alta y temperaturas templadas"


def _store(tmp_path):
    s = Judgments(tmp_path / "j.jsonl")
    s.add({"qid": "t001", "doc_id": "d1", "paginas": [3], "hash": text_hash(TEXT), "texto": TEXT, "grado": 2,
           "fuente": "juez", "firma": "x", "chunk_id": "c1"})
    s.add({"qid": "t001", "doc_id": "d2", "paginas": [9], "hash": text_hash("otro tema sin relación alguna aquí"),
           "texto": "otro tema sin relación alguna aquí", "grado": 0, "fuente": "juez", "firma": "x", "chunk_id": "c2"})
    return s


def test_grade_is_inherited_by_an_overlapping_fragment_of_another_chunking(tmp_path):
    s = _store(tmp_path)
    assert s.grade("t001", "d1", [3], TEXT) == 2                                    # same text
    longer = "Sección 4. " + TEXT + " según los registros de campo de la zona."
    assert s.grade("t001", "d1", [3, 4], longer) == 2                               # other chunking, same passage
    assert s.grade("t001", "d1", [12], longer) is None                              # other page: not judged
    assert s.grade("t002", "d1", [3], TEXT) is None                                 # other question


def test_reload_keeps_judgments(tmp_path):
    _store(tmp_path)
    assert len(Judgments(tmp_path / "j.jsonl").rows) == 2


def test_graded_metrics(tmp_path):
    s = _store(tmp_path)
    m = graded_metrics([("d2", [9], "otro tema sin relación alguna aquí"), ("d1", [3], TEXT)], "t001", s)
    assert m["util@1"] == 0.0 and m["util@5"] == 1.0
    assert m["mrr@10"] == 0.5 and m["recall@5"] == 1.0
    assert 0 < m["ndcg@10"] < 1


def test_kappa():
    assert cohen_kappa([0, 1, 2, 2], [0, 1, 2, 2]) == 1.0
    assert cohen_kappa([0, 0, 1, 1], [1, 1, 0, 0]) < 0
