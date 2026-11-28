"""Suite S1, structured questions (protocol of Objetivo 2: at least 100 questions with an exact answer).

Questions are generated from the graph, which is loaded from the dated official snapshots, and the expected answer is
the value of the official table as stored there: the limit version in force (with its regulation and dates), the SIGIA
authorization (registration number, pre-harvest interval) or the FRAC/IRAC/HRAC group. Only cases with an explicit value
in the table are used, so the expected answer needs no interpretation by the system under test (the rules engine is not
used to build the answers). Generation is deterministic (seeded): the same graph gives the same suite.

Types: lmr_ue_vigente (30), lmr_ue_historico (10), lmr_eeuu (15), lmr_codex (10), comparacion (10), registro (15, 10 yes
and 5 no), carencia (10), modo_accion (10). The metric is exactness of value and unit (Objetivo 2, «Exactitud (S1)»)."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from knowledge.graph.age import AgeGraph
from knowledge.graph.queries import in_force, mrl_versions
from knowledge.normalization.ingredients import Aliases, spanish_names

CROPS = {"blueberry": "arándano", "avocado": "palto", "table_grape": "uva de mesa"}
MARKETS = {"EU": "la Unión Europea", "US": "Estados Unidos", "CODEX": "el Codex Alimentarius"}
COUNTS = {"lmr_ue_vigente": 30, "lmr_ue_historico": 10, "lmr_eeuu": 15, "lmr_codex": 10, "comparacion": 10,
          "registro": 15, "carencia": 10, "modo_accion": 10}


@dataclass
class StructuredItem:
    qid: str
    tipo: str
    pregunta: str
    esperado: dict                      # value, unit and the source fields that support it
    parametros: dict = field(default_factory=dict)


def _fmt(d: str | date) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d/%m/%Y")


class SuiteBuilder:
    def __init__(self, graph: AgeGraph, today: date, seed: int = 20261111):
        self.g, self.today, self.rng = graph, today, random.Random(seed)
        self.es = spanish_names(Aliases.load())
        import yaml

        from knowledge.corpus.sources import CONFIG
        self.es_extra = yaml.safe_load((CONFIG / "ingredient_nombres_es.yaml").read_text(encoding="utf-8")) or {}
        self._spelling = "iso"
        self.items: list[StructuredItem] = []

    def name(self, iso: str) -> str:
        """The official SIGIA spelling (ISO, as SENASA writes it) or the common Spanish name, alternating (seeded), so
        the suite also tests that the system normalizes both. The choice is kept per item in «grafia»."""
        es = self.es.get(iso) or (self.es_extra.get(iso) or {}).get("es")
        self._spelling = "es" if es and self.rng.random() < 0.5 else "iso"
        return es if self._spelling == "es" else iso

    def add(self, tipo: str, pregunta: str, esperado: dict, **params) -> None:
        if "ingrediente" in params:
            params["grafia"] = self._spelling
        self.items.append(StructuredItem(f"s{len(self.items) + 1:03d}", tipo, pregunta, esperado, params))

    # candidates -------------------------------------------------------------------------------------------------
    def _pairs(self, market: str) -> list[tuple[str, str]]:
        """(ingredient, crop) with at least one numeric limit version in the market."""
        rows = self.g.run(
            "MATCH (i:Ingredient)-[:MEASURED_AS]->(:Residue)<-[:OF_RESIDUE]-(m:MrlVersion)-[:FOR_CROP]->(c:Crop), "
            "(m)-[:IN_MARKET]->(:Market {key: $market}) WHERE m.value_mg_kg IS NOT NULL "
            "RETURN DISTINCT i.key, c.key", {"market": market}, columns=("i", "c"))
        return sorted((r[0], r[1]) for r in rows if r[1] in CROPS)

    def _single_in_force(self, ing: str, crop: str, market: str, day: date) -> dict | None:
        """The version in force on ``day`` when exactly one residue definition applies (otherwise ambiguous)."""
        live = [m for m in mrl_versions(self.g, ing, crop, market) if in_force(m, day.isoformat())]
        if len({m.get("residue") for m in live}) != 1 or len(live) != 1 or live[0].get("value_mg_kg") is None:
            return None
        return live[0]

    # generators -------------------------------------------------------------------------------------------------
    def mrl(self, tipo: str, market: str, n: int) -> None:
        pairs = self._pairs(market)
        self.rng.shuffle(pairs)
        for ing, crop in pairs:
            if sum(1 for i in self.items if i.tipo == tipo) >= n:
                return
            m = self._single_in_force(ing, crop, market, self.today)
            if not m:
                continue
            self.add(tipo, f"¿Cuál es el límite máximo de residuos de {self.name(ing)} en {CROPS[crop]} en "
                           f"{MARKETS[market]}, vigente al {_fmt(self.today)}?",
                     {"valor_mg_kg": m["value_mg_kg"], "unidad": "mg/kg", "texto_oficial": m.get("value_text"),
                      "norma": m.get("regulation"), "aplica_desde": m.get("applies_from"), "residuo": m.get("residue"),
                      "en_limite_de_determinacion": m.get("at_limit_of_determination"), "instantanea": m.get("snapshot")},
                     ingrediente=ing, cultivo=crop, mercado=market, fecha=self.today.isoformat())

    def mrl_history(self, n: int) -> None:
        pairs = self._pairs("EU")
        self.rng.shuffle(pairs)
        for ing, crop in pairs:
            if sum(1 for i in self.items if i.tipo == "lmr_ue_historico") >= n:
                return
            vs = [m for m in mrl_versions(self.g, ing, crop, "EU") if m.get("applies_from") and m.get("value_mg_kg") is not None]
            if len({m.get("residue") for m in vs}) != 1 or len(vs) < 2:
                continue
            old, new = vs[1], vs[0]                     # newest first
            if old["value_mg_kg"] == new["value_mg_kg"]:
                continue
            day = date.fromisoformat(new["applies_from"]) - timedelta(days=30)
            m = self._single_in_force(ing, crop, "EU", day)
            if not m or m["value_mg_kg"] != old["value_mg_kg"]:
                continue
            self.add("lmr_ue_historico", f"¿Qué límite máximo de residuos de {self.name(ing)} en {CROPS[crop]} regía en la "
                                         f"Unión Europea el {_fmt(day)}?",
                     {"valor_mg_kg": m["value_mg_kg"], "unidad": "mg/kg", "norma": m.get("regulation"),
                      "aplica_desde": m.get("applies_from"), "valor_vigente_hoy": new["value_mg_kg"],
                      "cambio_desde": new["applies_from"], "instantanea": m.get("snapshot")},
                     ingrediente=ing, cultivo=crop, mercado="EU", fecha=day.isoformat())

    def comparison(self, n: int) -> None:
        both = sorted(set(self._pairs("EU")) & set(self._pairs("US")))
        self.rng.shuffle(both)
        for ing, crop in both:
            if sum(1 for i in self.items if i.tipo == "comparacion") >= n:
                return
            eu, us = (self._single_in_force(ing, crop, mk, self.today) for mk in ("EU", "US"))
            if not eu or not us or eu["value_mg_kg"] == us["value_mg_kg"]:
                continue
            stricter = "EU" if eu["value_mg_kg"] < us["value_mg_kg"] else "US"
            self.add("comparacion", f"Para {self.name(ing)} en {CROPS[crop]}, ¿qué mercado tiene el límite más estricto "
                                    f"al {_fmt(self.today)}, la Unión Europea o Estados Unidos, y cuáles son ambos valores?",
                     {"mercado_mas_estricto": stricter, "ue_mg_kg": eu["value_mg_kg"], "eeuu_mg_kg": us["value_mg_kg"],
                      "unidad": "mg/kg", "norma_ue": eu.get("regulation"), "norma_eeuu": us.get("regulation")},
                     ingrediente=ing, cultivo=crop, fecha=self.today.isoformat())

    def registrations(self, n_yes: int, n_no: int) -> None:
        rows = self.g.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(p:Product), (a)-[:ON_CROP]->(c:Crop), (a)-[:AGAINST]->(t:Pest) "
            "WHERE t.other_use = false RETURN p.key, p.trade_name, p.registration_number, c.key, t.key, t.common_name, "
            "t.scientific_name", columns=("p", "name", "reg", "crop", "pest", "pc", "ps"))
        rows = sorted(rows)
        self.rng.shuffle(rows)
        registered = {(r[0], r[3], r[4]) for r in rows}
        yes = 0
        for p, name, reg, crop, pest, pc, ps in rows:
            if yes >= n_yes:
                break
            if crop not in CROPS or not name:
                continue
            self.add("registro", f"¿Está registrado en el SENASA el producto {name} para {CROPS[crop]} contra "
                                 f"{pc} ({ps})?", {"registrado": True, "numero_registro": reg},
                     producto=p, cultivo=crop, plaga=pest)
            yes += 1
        no = 0
        for p, name, reg, crop, pest, pc, ps in rows:      # same product and pest, another crop where it is not registered
            if no >= n_no:
                break
            other = next((c for c in CROPS if c != crop and (p, c, pest) not in registered
                          and not any(k[0] == p and k[1] == c for k in registered)), None)
            if not other or not name:
                continue
            self.add("registro", f"¿Está registrado en el SENASA el producto {name} para {CROPS[other]} contra "
                                 f"{pc} ({ps})?", {"registrado": False, "registrado_en_otro_cultivo": CROPS[crop]},
                     producto=p, cultivo=other, plaga=pest)
            no += 1

    def preharvest(self, n: int) -> None:
        rows = self.g.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(p:Product), (a)-[:ON_CROP]->(c:Crop) "
            "WHERE a.preharvest_interval_days IS NOT NULL RETURN p.key, p.trade_name, c.key, "
            "collect(DISTINCT a.preharvest_interval_days)", columns=("p", "name", "crop", "phis"))
        rows = sorted((r for r in rows if r[2] in CROPS and len(r[3]) == 1 and r[1]), key=lambda r: (r[0], r[2]))
        self.rng.shuffle(rows)
        for p, name, crop, phis in rows[:n]:
            self.add("carencia", f"¿Cuál es el periodo de carencia del producto {name} en {CROPS[crop]} según su registro "
                                 f"en el SENASA?", {"dias": phis[0], "unidad": "días"}, producto=p, cultivo=crop)

    def moa(self, n: int) -> None:
        rows = self.g.run("MATCH (i:Ingredient)-[:IN_GROUP]->(g:MoaGroup) RETURN i.key, collect(g.key)",
                          columns=("i", "groups"))
        rows = sorted((r for r in rows if len(r[1]) == 1 and r[0] in self.es), key=lambda r: r[0])
        self.rng.shuffle(rows)
        for ing, groups in rows[:n]:
            scheme, code = groups[0].split(":", 1)
            self.add("modo_accion", f"¿A qué grupo de modo de acción del {scheme} pertenece {self.name(ing)}?",
                     {"esquema": scheme, "grupo": code}, ingrediente=ing)

    def build(self) -> list[StructuredItem]:
        self.mrl("lmr_ue_vigente", "EU", COUNTS["lmr_ue_vigente"])
        self.mrl_history(COUNTS["lmr_ue_historico"])
        self.mrl("lmr_eeuu", "US", COUNTS["lmr_eeuu"])
        self.mrl("lmr_codex", "CODEX", COUNTS["lmr_codex"])
        self.comparison(COUNTS["comparacion"])
        self.registrations(10, 5)
        self.preharvest(COUNTS["carencia"])
        self.moa(COUNTS["modo_accion"])
        return self.items


def build_suite(graph: AgeGraph, today: date) -> list[dict]:
    return [asdict(i) for i in SuiteBuilder(graph, today).build()]
