"""Suite S1b: list and count questions that the six original tools cannot answer (rule in pendientes/26, 27/11/2026).

Three kinds, all built from the graph with their own queries (not with the tools under test) and a fixed seed:

- ``lista``: «¿Qué productos registrados en el SENASA para {cultivo} contra {plaga} tienen un periodo de carencia de N
  días o menos?», for crop, pest and N where 2 to 4 products qualify among at least 5 registered. A product qualifies
  when every registration of it for that pest gives an interval and the longest one is N or less.
- ``conteo_productos``: «¿Cuántos productos están registrados en el SENASA para {cultivo} contra {plaga}?».
- ``conteo_sin_lmr``: «¿Cuántos ingredientes activos de los productos registrados para {cultivo} no tienen un LMR
  vigente en {mercado}?», for every crop and market, on the reference date.

The pest is named by its scientific name, and only names that designate the same pests whether read exactly or word
by word are used, so the question is not ambiguous. A list answer is exact when it names every expected product and
none of the other products registered for that pest; a count answer, when it gives the number."""
from __future__ import annotations

import random
import re
import unicodedata
from datetime import date

from knowledge.graph.queries import in_force, mrl_versions

CULTIVO_ES = {"blueberry": "arándano", "avocado": "palto", "table_grape": "uva de mesa"}
MERCADO_ES = {"EU": "la Unión Europea", "US": "Estados Unidos", "CODEX": "el Codex Alimentarius"}
CORTES = (1, 3, 7, 14, 21)


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in t).split())


def _plagas(graph, crop: str) -> list[tuple[str, str, str]]:
    return [r for r in graph.run(
        "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:AGAINST]->(t:Pest) "
        "RETURN DISTINCT t.key, t.common_name, t.scientific_name", {"c": crop}, columns=("k", "c", "s"))
        if not str(r[0]).startswith("use:") and r[2]]


def _grupos(plagas: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    """Scientific name -> pest keys, kept only when the exact name and the word-by-word reading give the same pests."""
    out = {}
    for sci in sorted({_norm(s) for _, _, s in plagas}):
        palabras = sci.split()
        if len(palabras) < 2 or any(len(w) < 4 for w in palabras):          # «Erysiphe sp» and the like are left out
            continue
        exactos = sorted(k for k, _, s in plagas if _norm(s) == sci)
        por_palabra = sorted(k for k, c, s in plagas
                             if all(any(x.startswith(w) for x in _norm(f"{c} {s}").split()) for w in palabras))
        if exactos and exactos == por_palabra:
            out[sci] = exactos
    return out


def _productos(graph, crop: str, pests: list[str]) -> dict[str, tuple[str, int | None]]:
    """Product key -> (trade name, interval for these pests: the longest, None if any registration lacks it)."""
    filas = graph.run(
        "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:AGAINST]->(t:Pest), (a)-[:OF_PRODUCT]->(p:Product) "
        "WHERE t.key IN $t RETURN p.key, p.trade_name, a.preharvest_interval_days",
        {"c": crop, "t": pests}, columns=("k", "n", "phi"))
    por: dict[str, tuple[str, list]] = {}
    for k, nombre, phi in filas:
        por.setdefault(k, (nombre, []))[1].append(phi)
    return {k: (n, None if None in phis else max(phis)) for k, (n, phis) in por.items()}


def _sin_lmr(graph, crop: str, market: str, dia: str) -> int:
    ings = {r[0] for r in graph.run(
        "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $c}), (a)-[:OF_PRODUCT]->(:Product)-[:CONTAINS]->(i:Ingredient) "
        "RETURN DISTINCT i.key", {"c": crop}, columns=("i",))}
    return sum(1 for i in ings if not [m for m in mrl_versions(graph, i, crop, market) if in_force(m, dia)])


def build(graph, hoy: date, seed: int = 20261127, n_listas: int = 12, n_conteos: int = 10,
          excluir: frozenset = frozenset(), fecha_conteos: date | None = None) -> list[dict]:
    """``excluir``: (kind, crop, pest) of an earlier suite, left out so that a new suite asks about other pests.
    ``fecha_conteos``: the counts of ingredients without a limit on that date, which the question then states."""
    rng = random.Random(seed)
    listas, conteos = [], []
    for crop in CULTIVO_ES:
        plagas = _plagas(graph, crop)
        nombres = {_norm(s): s for _, _, s in plagas}
        for sci, keys in _grupos(plagas).items():
            prods = _productos(graph, crop, keys)
            if 3 <= len(prods) <= 80 and ("conteo_productos", crop, nombres[sci]) not in excluir:
                conteos.append({"tipo": "conteo_productos", "cultivo": crop, "plaga": nombres[sci], "plagas": keys,
                                "esperado": len(prods)})
            if len(prods) < 5 or ("lista", crop, nombres[sci]) in excluir:
                continue
            for n in CORTES:
                ok = sorted(nombre for nombre, phi in prods.values() if phi is not None and phi <= n)
                if 2 <= len(ok) <= 4:
                    otros = sorted(nombre for nombre, _ in prods.values() if nombre not in ok)
                    listas.append({"tipo": "lista", "cultivo": crop, "plaga": nombres[sci], "plagas": keys,
                                   "carencia_maxima": n, "esperado": ok, "otros": otros})
                    break                               # one cut per pest: the smallest that gives a short list
    items = rng.sample(listas, min(n_listas, len(listas))) + rng.sample(conteos, min(n_conteos, len(conteos)))
    dia = (fecha_conteos or hoy).isoformat()
    for crop in CULTIVO_ES:
        for market in MERCADO_ES:
            items.append({"tipo": "conteo_sin_lmr", "cultivo": crop, "mercado": market, "fecha": dia,
                          "esperado": _sin_lmr(graph, crop, market, dia)})
    out = []
    for i, it in enumerate(items, 1):
        c = CULTIVO_ES[it["cultivo"]]
        if it["tipo"] == "lista":
            q = (f"¿Qué productos registrados en el SENASA para {c} contra {it['plaga']} tienen un periodo de carencia de "
                 f"{it['carencia_maxima']} días o menos?")
        elif it["tipo"] == "conteo_productos":
            q = f"¿Cuántos productos están registrados en el SENASA para {c} contra {it['plaga']}?"
        elif fecha_conteos:
            q = (f"¿Cuántos ingredientes activos de los productos registrados para {c} no tendrán un LMR vigente en "
                 f"{MERCADO_ES[it['mercado']]} el {fecha_conteos:%d/%m/%Y}?")
        else:
            q = (f"¿Cuántos ingredientes activos de los productos registrados para {c} no tienen un LMR vigente en "
                 f"{MERCADO_ES[it['mercado']]}?")
        out.append({"qid": f"g{i:03d}", "pregunta": q, **it})
    return out


def _nombrado(nombre: str, texto: str, primeras: dict[str, int]) -> bool:
    """The trade name appears whole, or its first word does when it is long and no other candidate starts with it."""
    n, t = _norm(nombre), f" {_norm(texto)} "
    if f" {n} " in t:
        return True
    primera = n.split()[0] if n else ""
    return len(primera) >= 4 and primeras.get(primera, 0) == 1 and f" {primera} " in t


def exacta(item: dict, texto: str) -> bool:
    if item["tipo"] == "lista":
        primeras: dict[str, int] = {}
        for nombre in item["esperado"] + item["otros"]:
            p = _norm(nombre).split()[0] if _norm(nombre) else ""
            primeras[p] = primeras.get(p, 0) + 1
        return (all(_nombrado(x, texto, primeras) for x in item["esperado"])
                and not any(_nombrado(x, texto, primeras) for x in item["otros"]))
    return re.search(rf"(?<![\d.,]){item['esperado']}(?![\d]|[.,]\d)", texto or "") is not None
