from knowledge.vocabulary.index import Term, Vocabulary


def _vocab():
    terms = {("pest", "p1"): Term("pest", "p1", {"Erysiphe necator", "Oidiosis", "oídio de la vid", "Oídio de la vid"}),
             ("pest", "p2"): Term("pest", "p2", {"Podosphaera xanthii", "Oidiosis"})}
    by_label = {}
    from knowledge.vocabulary.agrovoc import norm
    for k, t in terms.items():
        for lab in t.labels:
            by_label.setdefault(norm(lab), [])
            if k not in by_label[norm(lab)]:
                by_label[norm(lab)].append(k)
    return Vocabulary(terms, by_label)


def test_pairs_skip_ambiguous_and_duplicate_labels():
    rows = _vocab().pairs()
    labels = {x for r in rows for x in (r["anchor"], r["positive"])}
    assert "Oidiosis" not in labels                      # names two pests: would teach a false equivalence
    p1 = [r for r in rows if r["key"] == "p1"]
    assert len(p1) == 1 and {p1[0]["anchor"], p1[0]["positive"]} == {"Erysiphe necator", "Oídio de la vid"} or \
           {p1[0]["anchor"], p1[0]["positive"]} == {"Erysiphe necator", "oídio de la vid"}
    assert not [r for r in rows if r["key"] == "p2"]     # only one unambiguous label left: no pair


def test_pairs_cap_per_term():
    v = Vocabulary({("ingredient", "x"): Term("ingredient", "x", {"aaaa", "bbbb", "cccc", "dddd", "eeee"})},
                   {n: [("ingredient", "x")] for n in ("aaaa", "bbbb", "cccc", "dddd", "eeee")})
    assert len(v.pairs(max_per_term=3)) == 3 and len(v.pairs()) == 6
