from evaluation.comparacion import mcnemar_exacta, wilcoxon


def test_mcnemar_counts_discordant_pairs_and_is_two_sided():
    r = mcnemar_exacta([True] * 10 + [False] * 2, [False] * 10 + [False] * 2)
    assert r["solo_a"] == 10 and r["solo_b"] == 0 and abs(r["p"] - 2 / 2 ** 10) < 1e-12


def test_mcnemar_identical_systems_give_p_one():
    assert mcnemar_exacta([True, False], [True, False])["p"] == 1.0


def test_wilcoxon_detects_a_consistent_shift_and_ignores_zeros():
    x = [0.9, 0.8, 0.85, 0.95, 0.7, 0.9, 0.88, 0.92, 0.81, 0.87, 0.5]
    y = [0.5, 0.4, 0.45, 0.55, 0.3, 0.5, 0.48, 0.52, 0.41, 0.47, 0.5]
    r = wilcoxon(x, y)
    assert r["n"] == 10 and r["p"] < 0.01
