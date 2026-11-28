"""Paired comparisons for the short paper (rules in pendientes/26, 24/11/2026), computed with SciPy so they can be
checked with standard tools.

- McNemar, exact two-sided: a binomial test on the discordant pairs (scipy.stats.binomtest, p = 0.5).
- Wilcoxon signed-rank, two-sided (scipy.stats.wilcoxon, zero differences dropped as in Wilcoxon's original method),
  on per-question faithfulness over the questions both systems answered with evidence.
"""
from __future__ import annotations

from scipy.stats import binomtest
from scipy.stats import wilcoxon as _wilcoxon


def mcnemar_exacta(a: list[bool], b: list[bool]) -> dict:
    """a and b: correctness of two systems on the same questions, in the same order."""
    solo_a = sum(1 for x, y in zip(a, b) if x and not y)
    solo_b = sum(1 for x, y in zip(a, b) if y and not x)
    n = solo_a + solo_b
    p = 1.0 if n == 0 else float(binomtest(min(solo_a, solo_b), n, 0.5, alternative="two-sided").pvalue)
    return {"solo_a": solo_a, "solo_b": solo_b, "p": p, "prueba": "McNemar exacta (scipy.stats.binomtest)"}


def wilcoxon(x: list[float], y: list[float]) -> dict:
    """Signed-rank test of x - y over paired values."""
    d = [a - b for a, b in zip(x, y)]
    n = sum(1 for v in d if v != 0)
    if n == 0:
        return {"n": 0, "estadistico": 0.0, "p": 1.0, "prueba": "Wilcoxon (scipy.stats.wilcoxon)"}
    r = _wilcoxon(x, y, zero_method="wilcox", alternative="two-sided")
    return {"n": n, "estadistico": float(r.statistic), "p": float(r.pvalue), "prueba": "Wilcoxon (scipy.stats.wilcoxon)"}
