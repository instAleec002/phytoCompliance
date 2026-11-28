"""Wilson intervals, bootstrap intervals and the Holm correction."""
from evaluation.estadistica import bootstrap_media, holm, wilson


def test_wilson_handles_all_and_none():
    lo, hi = wilson(110, 110)
    assert round(lo, 3) == 0.966 and hi == 1.0
    lo, hi = wilson(0, 31)
    assert lo == 0.0 and round(hi, 3) == 0.110


def test_holm_is_step_down_and_monotone():
    assert holm([0.01, 0.04, 0.03, 0.5]) == [0.04, 0.09, 0.09, 0.5]
    assert holm([0.2]) == [0.2] and holm([0.6, 0.6]) == [1.0, 1.0]


def test_bootstrap_interval_contains_the_mean_and_is_fixed_by_the_seed():
    v = [0.0, 0.5, 1.0, 1.0, 0.25, 0.75]
    lo, hi = bootstrap_media(v, b=2000)
    assert lo <= sum(v) / len(v) <= hi and bootstrap_media(v, b=2000) == (lo, hi)
