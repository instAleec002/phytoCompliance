"""Intervals and multiple-comparison correction for the reported results (rule in pendientes/26, 27/11/2026).

- ``wilson``: 95 % interval of a proportion (good with small n and with 0 or n successes, unlike the normal one);
- ``bootstrap_media``: 95 % percentile interval of a mean, resampling the items (questions or answers) with a fixed
  seed;
- ``holm``: Holm-Bonferroni adjusted p-values for one family of tests (step-down, monotone, capped at 1)."""
from __future__ import annotations

import math
import random
import statistics


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    lo, hi = max(0.0, centro - margen), min(1.0, centro + margen)
    return (0.0 if k == 0 else lo, 1.0 if k == n else hi)


def bootstrap_media(valores: list[float], b: int = 10_000, semilla: int = 20261127) -> tuple[float, float]:
    if not valores:
        return (math.nan, math.nan)
    rng = random.Random(semilla)
    n = len(valores)
    medias = sorted(statistics.fmean(rng.choices(valores, k=n)) for _ in range(b))
    return (medias[int(0.025 * b)], medias[int(0.975 * b) - 1])


def holm(pvalores: list[float]) -> list[float]:
    """Adjusted p-values in the order given."""
    m = len(pvalores)
    orden = sorted(range(m), key=lambda i: pvalores[i])
    ajustados = [0.0] * m
    previo = 0.0
    for rango, i in enumerate(orden):
        previo = max(previo, min(1.0, (m - rango) * pvalores[i]))
        ajustados[i] = previo
    return ajustados
