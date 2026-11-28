from interfaces.jobs.evaluate import split_s2


def _items():
    return ([{"qid": f"u{i:02d}", "tipo": "un_salto"} for i in range(40)]
            + [{"qid": f"m{i:02d}", "tipo": "varios_saltos"} for i in range(20)])


def test_split_is_stratified_30_70():
    s = split_s2(_items())
    assert len(s["desarrollo"]) == 18 and len(s["prueba"]) == 42
    assert sum(q.startswith("m") for q in s["desarrollo"]) == 6      # 30 % of the 20 multi-hop questions
    assert not set(s["desarrollo"]) & set(s["prueba"])


def test_split_does_not_depend_on_order_and_changes_with_seed():
    a = split_s2(_items())
    assert split_s2(list(reversed(_items()))) == a
    assert split_s2(_items(), seed=1)["desarrollo"] != a["desarrollo"]
