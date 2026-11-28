"""Suite S3, spray programs with seeded violations (protocol of Objetivo 2: at least 20 programs).

Each case starts from a clean program built from the graph: one crop, two blocks with their harvest date and markets,
and applications of products registered for that crop and pest, applied well before harvest, with alternating modes of
action. «Clean» is checked by running the validator: the base may only have INFO findings. Then one or two violations
are seeded on purpose, and the expected answer is the list of seeded violations (code, block, product), known by
construction. The validator is used only to confirm the base is clean and to record, for transparency, any collateral
finding a seeded change brings (for example, a swapped product that also lacks a limit in one market).

Seeded kinds (codes of domain.validation): NOT_REGISTERED, PHI_NOT_MET, APPLIED_AFTER_HARVEST, ROTATION_SAME_GROUP,
UNKNOWN_BLOCK. S3 measures, for the system under test, recall and precision over the seeded violations."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta

from domain.findings import Severity
from domain.validation.models import Application, Block, Program
from domain.validation.program import validate_program

KINDS = ("NOT_REGISTERED", "PHI_NOT_MET", "APPLIED_AFTER_HARVEST", "ROTATION_SAME_GROUP", "UNKNOWN_BLOCK")
MARKETS = (("EU",), ("US",), ("EU", "US"))


@dataclass
class ProgramCase:
    pid: str
    cultivo: str
    programa: dict                                   # blocks and applications, as the API receives them
    sembradas: list[dict]                            # expected: code, block, product
    colaterales: list[dict] = field(default_factory=list)
    descripcion: str = ""


def _as_dict(p: Program) -> dict:
    return {"crop": p.crop,
            "blocks": [{"key": b.key, "harvest_on": b.harvest_on.isoformat(), "markets": list(b.markets)} for b in p.blocks],
            "applications": [{"block": a.block, "product_id": a.product_id, "applied_on": a.applied_on.isoformat(),
                              "pest": a.pest} for a in p.applications]}


class ProgramSuiteBuilder:
    def __init__(self, graph, sources, seed: int = 20261111, harvest: date = date(2027, 1, 15)):
        self.g, self.s, self.rng, self.harvest = graph, sources, random.Random(seed), harvest

    def _candidates(self, crop: str) -> list[tuple[str, str, int, tuple[str, ...]]]:
        """(product, pest, PHI days, MoA groups) for chemical products registered on the crop with a known PHI and a
        single classified group, so rotation is checkable."""
        rows = self.g.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(p:Product), (a)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(t:Pest) "
            "WHERE a.preharvest_interval_days IS NOT NULL AND t.other_use = false AND p.product_type = 'QUIMICO' "
            "MATCH (p)-[:CONTAINS]->(i:Ingredient)-[:IN_GROUP]->(g:MoaGroup) "
            "RETURN p.key, t.key, a.preharvest_interval_days, collect(DISTINCT g.key)", {"crop": crop},
            columns=("p", "t", "phi", "groups"))
        return sorted((p, t, int(phi), tuple(sorted(gs))) for p, t, phi, gs in rows if gs and phi is not None and phi <= 30)

    def _validate(self, program: Program):
        return validate_program(program, self.s.registry, self.s.limits, self.s.moa)

    def _clean_base(self, crop: str, markets: tuple[str, ...]) -> Program | None:
        cands = self._candidates(crop)
        self.rng.shuffle(cands)
        apps, last_groups = [], {}
        blocks = (Block("A1", self.harvest, markets), Block("B2", self.harvest + timedelta(days=10), markets))
        for b in blocks:
            day = b.harvest_on - timedelta(days=90)
            for p, t, phi, gs in cands:
                if len([a for a in apps if a.block == b.key]) >= 3:
                    break
                if set(gs) & set(last_groups.get(b.key, ())):
                    continue
                trial = Application(b.key, p, day, t)
                one = Program(crop, blocks, (trial,))
                if any(f.severity in (Severity.BLOCKING, Severity.RISK) for f in self._validate(one).findings):
                    continue                     # this product already brings a limit or registration problem
                apps.append(trial)
                last_groups[b.key] = gs
                day += timedelta(days=14)
        base = Program(crop, blocks, tuple(apps))
        if len(apps) < 6 or any(f.severity in (Severity.BLOCKING, Severity.RISK) for f in self._validate(base).findings):
            return None
        return base

    def _seed(self, base: Program, kind: str, crop: str) -> tuple[Program, dict, str] | None:
        apps = list(base.applications)
        i = self.rng.randrange(len(apps))
        a = apps[i]
        blk = base.block(a.block)
        if kind == "NOT_REGISTERED":
            others = [k for k in ("blueberry", "avocado", "table_grape") if k != crop]
            for other in others:
                for p, t, phi, gs in self._candidates(other):
                    if self.s.registry.registration(p, crop, t) is None and self.s.registry.registration(p, crop) is None:
                        apps[i] = replace(a, product_id=p, pest=a.pest)
                        return replace(base, applications=tuple(apps)), {"code": kind, "block": a.block, "product_id": p}, \
                            f"un producto registrado para {other} pero no para {crop}"
            return None
        if kind == "PHI_NOT_MET":
            reg = self.s.registry.registration(a.product_id, crop, a.pest)
            phi = reg.preharvest_interval_days if reg else None
            if not phi or phi < 2:
                return None
            apps[i] = replace(a, applied_on=blk.harvest_on - timedelta(days=max(1, phi // 2)))
            return replace(base, applications=tuple(apps)), {"code": kind, "block": a.block, "product_id": a.product_id}, \
                f"aplicado a la mitad de su carencia de {phi} días antes de la cosecha"
        if kind == "APPLIED_AFTER_HARVEST":
            apps[i] = replace(a, applied_on=blk.harvest_on + timedelta(days=3))
            return replace(base, applications=tuple(apps)), {"code": kind, "block": a.block, "product_id": a.product_id}, \
                "aplicado tres días después de la cosecha"
        if kind == "ROTATION_SAME_GROUP":
            block_apps = sorted((x for x in apps if x.block == a.block), key=lambda x: x.applied_on)
            first = block_apps[0]
            dup = replace(first, applied_on=first.applied_on + timedelta(days=7))
            apps.append(dup)
            return replace(base, applications=tuple(apps)), {"code": kind, "block": a.block, "product_id": first.product_id}, \
                "el mismo producto repetido a los 7 días (mismo grupo de modo de acción dos veces seguidas)"
        if kind == "UNKNOWN_BLOCK":
            apps[i] = replace(a, block="Z9")
            return replace(base, applications=tuple(apps)), {"code": kind, "block": "Z9", "product_id": a.product_id}, \
                "una aplicación en un bloque que no existe en el programa"
        return None

    def build(self, n: int = 30) -> list[ProgramCase]:
        cases: list[ProgramCase] = []
        crops = ("blueberry", "avocado", "table_grape")
        attempts = 0
        while len(cases) < n and attempts < n * 6:
            attempts += 1
            crop = crops[len(cases) % 3]
            base = self._clean_base(crop, MARKETS[len(cases) % len(MARKETS)])
            if base is None:
                continue
            kinds = [KINDS[len(cases) % len(KINDS)]]
            if len(cases) % 3 == 2:                                  # a third of the cases carry two violations
                kinds.append(self.rng.choice([k for k in KINDS if k != kinds[0] and k != "UNKNOWN_BLOCK"]))
            program, seeded, desc = base, [], []
            for k in kinds:
                out = self._seed(program, k, crop)
                if out is None:
                    break
                program, s, d = out
                seeded.append(s)
                desc.append(d)
            if len(seeded) != len(kinds):
                continue
            found = self._validate(program).findings
            expected = {(s["code"], s["block"], s["product_id"]) for s in seeded}
            hit = {(f.code, f.block, f.product_id) for f in found}
            if not expected <= hit:
                continue                                             # the seeding did not produce what it claims
            collateral = [{"code": f.code, "block": f.block, "product_id": f.product_id, "severity": f.severity.name}
                          for f in found if (f.code, f.block, f.product_id) not in expected and f.severity is not Severity.INFO]
            cases.append(ProgramCase(f"p{len(cases) + 1:03d}", crop, _as_dict(program), seeded, collateral, "; ".join(desc)))
        return cases


def build_program_suite(graph, sources, n: int = 30) -> list[dict]:
    return [asdict(c) for c in ProgramSuiteBuilder(graph, sources).build(n)]


# controls (review of the short paper, 26/11/2026) -------------------------------------------------------------------
# The seeded suite only has programs with violations, so a validator that flagged everything would score the same. The
# controls add clean programs and near misses at the edges of the rules. Their expected outcome comes from the rules as
# SENASA and FRAC/IRAC state them (the harvest may happen once the pre-harvest interval has passed, so on the day
# ``applied + interval`` it is allowed; only consecutive applications of one group are a rotation problem), applied by
# date arithmetic here; the validator is never used to build or label them. Market-limit risks are out of these
# controls: they depend on each ingredient's limit, not on the edge being tested.
CONTROL_KINDS = ("LIMPIO", "PHI_EXACTA", "PHI_MENOS_UNO", "COSECHA_MISMO_DIA", "OTRA_PLAGA", "ROTACION_ALTERNA")


class ControlSuiteBuilder(ProgramSuiteBuilder):
    def __init__(self, graph, sources, seed: int = 20261126, harvest: date = date(2027, 1, 15)):
        super().__init__(graph, sources, seed, harvest)

    def _base(self, crop: str) -> tuple[Program, dict] | None:
        """Two blocks, three applications each, 90, 76 and 62 days before harvest (every interval used is 30 days or
        less), products registered for the crop and pest, and pairwise disjoint mode-of-action groups in each block."""
        cands = [c for c in self._candidates(crop) if c[2] >= 1]
        self.rng.shuffle(cands)
        blocks = (Block("A1", self.harvest, ("EU",)), Block("B2", self.harvest + timedelta(days=10), ("EU",)))
        apps, info = [], {}
        for b in blocks:
            used: set[str] = set()
            chosen = []
            for p, t, phi, gs in cands:
                if len(chosen) == 3:
                    break
                if set(gs) & used or any(p == c[0] for c in chosen):
                    continue
                chosen.append((p, t, phi, gs))
                used |= set(gs)
            if len(chosen) < 3:
                return None
            for k, (p, t, phi, gs) in enumerate(chosen):
                apps.append(Application(b.key, p, b.harvest_on - timedelta(days=90 - 14 * k), t))
                info[(b.key, p)] = {"phi": phi, "groups": gs, "pest": t}
        return Program(crop, blocks, tuple(apps)), info

    def _otra_plaga(self, crop: str, product: str, pest: str) -> str | None:
        pests = sorted({t for _, t, _, _ in self._candidates(crop) if t != pest})
        self.rng.shuffle(pests)
        return next((t for t in pests if self.s.registry.registration(product, crop, t) is None), None)

    def build_controls(self, n: int = 40) -> list[dict]:
        cases, crops, attempts = [], ("blueberry", "avocado", "table_grape"), 0
        while len(cases) < n and attempts < n * 8:
            attempts += 1
            if len(cases) < n // 3:
                kind = "LIMPIO"                    # a third clean, the rest the five near misses in turn
            else:
                kind = CONTROL_KINDS[1 + (len(cases) - n // 3) % (len(CONTROL_KINDS) - 1)]
            crop = crops[len(cases) % 3]
            built = self._base(crop)
            if built is None:
                continue
            base, info = built
            apps = list(base.applications)
            i = self.rng.randrange(len(apps))
            a = apps[i]
            blk = base.block(a.block)
            phi = info[(a.block, a.product_id)]["phi"]
            esperado, desc = [], "programa limpio"
            if kind == "PHI_EXACTA":
                apps[i] = replace(a, applied_on=blk.harvest_on - timedelta(days=phi))
                desc = f"aplicado exactamente {phi} días (su carencia) antes de la cosecha"
            elif kind == "PHI_MENOS_UNO":
                apps[i] = replace(a, applied_on=blk.harvest_on - timedelta(days=phi - 1))
                esperado = [{"code": "PHI_NOT_MET", "block": a.block, "product_id": a.product_id}]
                desc = f"aplicado {phi - 1} días antes de la cosecha, uno menos que su carencia de {phi}"
            elif kind == "COSECHA_MISMO_DIA":
                apps[i] = replace(a, applied_on=blk.harvest_on)
                esperado = [{"code": "PHI_NOT_MET", "block": a.block, "product_id": a.product_id}]
                desc = f"aplicado el mismo día de la cosecha (carencia {phi}); no es posterior a la cosecha"
            elif kind == "OTRA_PLAGA":
                otra = self._otra_plaga(crop, a.product_id, a.pest)
                if otra is None:
                    continue
                apps[i] = replace(a, pest=otra)
                esperado = [{"code": "NOT_REGISTERED", "block": a.block, "product_id": a.product_id}]
                desc = f"producto registrado para {crop} contra {a.pest}, usado contra {otra}, para la que no lo está"
            elif kind == "ROTACION_ALTERNA":
                same = sorted((x for x in apps if x.block == a.block), key=lambda x: x.applied_on)
                first = same[0]
                apps.append(replace(first, applied_on=same[-1].applied_on + timedelta(days=14)))
                desc = "el primer producto se repite después de otros dos grupos (no consecutivo)"
            cases.append({"pid": f"c{len(cases) + 1:03d}", "tipo": kind, "cultivo": crop,
                          "programa": _as_dict(replace(base, applications=tuple(apps))),
                          "esperadas": esperado, "descripcion": desc})
        return cases
