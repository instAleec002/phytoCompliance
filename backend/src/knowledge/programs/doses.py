"""The dose written in a field sheet against the dose registered in SIGIA (stage E, rule 2 in pendientes/26).

SIGIA registers each authorized use with a dose per hectare and per 200 L tank («cilindro»), in litres or kilograms
of product. A field dose is compared only when it states a comparable unit: a volume or a mass, per hectare or per
tank (``2 Lt/ha``, ``300 ml/Cil``, ``0.06Kg/ cil``). A bare number, a percentage or another basis is not compared.
A row resolved by ingredient could be any registered product with those ingredients, so its dose is checked against
all of them: it is outside only when it is outside every registered range. Outside the range marks the row for review
and never blocks, because the registered dose depends on the formulation and the sheet may round it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from knowledge.sources.sigia.parser import dose_range

# field units -> (kind, factor to litres or kilograms)
_UNIDADES = {"ml": ("L", 0.001), "cc": ("L", 0.001), "l": ("L", 1.0), "lt": ("L", 1.0), "lts": ("L", 1.0),
             "litro": ("L", 1.0), "litros": ("L", 1.0), "g": ("kg", 0.001), "gr": ("kg", 0.001), "grs": ("kg", 0.001),
             "kg": ("kg", 1.0), "k": ("kg", 1.0), "kl": ("kg", 1.0), "kilo": ("kg", 1.0), "kilos": ("kg", 1.0)}
_BASES = {"ha": "ha", "hectarea": "ha", "has": "ha", "cil": "cil", "cilindro": "cil", "cilindros": "cil"}
# SIGIA's own unit names; «kl» is how it writes kilograms (0.35-0.4 kl/ha with 0.07-0.08 per tank, five tanks a
# hectare, is a powder, not 350 litres)
_SIGIA = {"lt": "L", "litro": "L", "l": "L", "kl": "kg", "kg": "kg", "kilogramo": "kg", "k/ha": "kg"}
_DOSIS = re.compile(r"^\s*(\d+(?:[.,]\d+)?|[.,]\d+)\s*([a-z]+)?\s*(?:/\s*([a-z]+|200\s*l))?\s*$")


@dataclass(frozen=True)
class Dosis:
    valor: float
    unidad: str               # L | kg
    base: str                 # ha | cil


def leer_dosis(texto) -> Dosis | None:
    """``2 Lt/ha`` -> 2 L per hectare; ``300 ml/Cil`` -> 0.3 L per tank; a bare number or another unit -> None."""
    if texto is None:
        return None
    t = str(texto).lower().replace("í", "i").replace("á", "a").strip()
    m = _DOSIS.match(t)
    if not m or not m.group(2) or not m.group(3):
        return None
    unidad, base = _UNIDADES.get(m.group(2)), _BASES.get("cil" if m.group(3).startswith("200") else m.group(3))
    if not unidad or not base:
        return None
    return Dosis(float(m.group(1).replace(",", ".")) * unidad[1], unidad[0], base)


@dataclass
class ControlDosis:
    texto: str | None
    estado: str                                   # dentro | fuera_de_rango | no_comparable
    motivo: str | None = None
    registradas: list[str] = field(default_factory=list)


def _registradas(graph, productos: tuple[str, ...], cultivo: str, plaga: str | None) -> list[tuple[str, str, float, float]]:
    """(unit, basis, minimum, maximum) of every registered use of these products on the crop (of the pest when the
    row names one and the product is registered for it)."""
    rows = graph.run(
        "MATCH (a:Authorization)-[:OF_PRODUCT]->(p:Product), (a)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(x:Pest) "
        "WHERE p.key IN $products RETURN x.key, a.dose_unit, a.dose_per_hectare, a.dose_per_tank",
        {"crop": cultivo, "products": list(productos)}, columns=("x", "u", "h", "t"))
    if plaga and any(r[0] == plaga for r in rows):
        rows = [r for r in rows if r[0] == plaga]
    out = []
    for _, u, h, t in rows:
        unidad = _SIGIA.get(str(u or "").strip().lower())
        if not unidad:
            continue
        for base, raw in (("ha", h), ("cil", t)):
            r = dose_range(raw) if raw else None
            if r and r.minimum is not None:
                out.append((unidad, base, r.minimum, r.maximum))
    return out


def _fmt(x: float) -> str:
    return f"{x:g}"


def controlar(graph, texto, productos: tuple[str, ...], cultivo: str, plaga: str | None = None) -> ControlDosis:
    d = leer_dosis(texto)
    if d is None:
        return ControlDosis(texto, "no_comparable", "la dosis no indica volumen o peso por hectárea o por cilindro"
                            if texto else "sin dosis")
    if not productos:
        return ControlDosis(texto, "no_comparable", "producto sin resolver")
    reg = _registradas(graph, productos, cultivo, plaga)
    misma = sorted({r for r in reg if r[0] == d.unidad and r[1] == d.base})
    textos = [f"{_fmt(lo)}" + (f"–{_fmt(hi)}" if hi != lo else "") + f" {u}/{'ha' if b == 'ha' else 'cilindro'}"
              for u, b, lo, hi in misma]
    if not misma:
        return ControlDosis(texto, "no_comparable",
                            f"SIGIA no registra dosis en {d.unidad}/{'ha' if d.base == 'ha' else 'cilindro'} "
                            "para este producto en el cultivo")
    if any(lo - 1e-9 <= d.valor <= hi + 1e-9 for _, _, lo, hi in misma):
        return ControlDosis(texto, "dentro", None, textos)
    return ControlDosis(texto, "fuera_de_rango", f"{_fmt(d.valor)} {d.unidad} fuera de lo registrado", textos)
