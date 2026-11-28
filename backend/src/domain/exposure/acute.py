"""Short-term (acute) dietary intake of a residue, IESTI, as EFSA PRIMo revision 3.1 computes it.

With R the residue (mg/kg), LP the large portion and U the unit weight of the edible portion (kg), bw the body
weight and v the variability factor:
- case 1 (unit weight below 25 g, or blended): IESTI = LP x R / bw (LP per kg bw: LP x R);
- case 2a (unit smaller than the large portion): IESTI = [U x R x v + (LP - U) x R] / bw;
- case 2b (unit at least as large as the large portion): IESTI = LP x R x v / bw.
The result in % of the ARfD is computed for every population (children, adults) and the highest one counts, as the
most critical consumer group decides. The residue is the one measured in the whole commodity; no peeling factor is
applied (conservative for avocado, whose peel is not eaten).
"""
from __future__ import annotations

from dataclasses import dataclass

from domain.ports import AcuteIntakeData


class UnknownCase(ValueError):
    pass


@dataclass(frozen=True)
class AcuteIntake:
    population: str
    diet: str
    case: str
    iesti_mg_kg_bw: float
    percent_of_arfd: float


def iesti(residue_mg_kg: float, c: AcuteIntakeData) -> float:
    lp_kg, bw = c.lp_g_person / 1000, c.bw_kg
    if c.case == "1":
        return c.lp_g_kg_bw / 1000 * residue_mg_kg
    if c.unit_edible_g is None:
        raise UnknownCase(f"case {c.case} needs the unit weight ({c.commodity}, {c.population})")
    u_kg, v = c.unit_edible_g / 1000, c.variability_factor
    if c.case == "2a":
        return (u_kg * residue_mg_kg * v + (lp_kg - u_kg) * residue_mg_kg) / bw
    if c.case == "2b":
        return lp_kg * residue_mg_kg * v / bw
    raise UnknownCase(f"IESTI case {c.case!r} not handled ({c.commodity}, {c.population})")


def acute_intakes(residue_mg_kg: float, arfd_mg_kg_bw: float, consumption: list[AcuteIntakeData]) -> list[AcuteIntake]:
    out = []
    for c in consumption:
        value = iesti(residue_mg_kg, c)
        out.append(AcuteIntake(c.population, c.diet, c.case, value, 100 * value / arfd_mg_kg_bw))
    return sorted(out, key=lambda a: -a.percent_of_arfd)
