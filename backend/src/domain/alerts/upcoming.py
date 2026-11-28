"""Early alerts: limits already published that will apply later ("Not yet applicable" in the EU database).

An alert compares the limit in force today with the new one and says whether it gets stricter, and whether it applies
before the harvest of a block that uses the ingredient, which is when it changes what the program may contain.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from domain.compliance.limits import limit_on, upcoming
from domain.compliance.models import MrlRecord
from domain.ports import LimitSource, RegistrySource
from domain.validation.models import Program


@dataclass(frozen=True)
class Alert:
    ingredient: str
    crop: str
    market: str
    applies_from: date
    current_mg_kg: float | None
    new_mg_kg: float | None
    new_no_mrl_required: bool
    regulation: str
    snapshot: str | None
    blocks_affected: tuple[str, ...] = ()

    @property
    def stricter(self) -> bool:
        if self.new_no_mrl_required:
            return False
        if self.new_mg_kg is None:
            return False
        return self.current_mg_kg is None or self.new_mg_kg < self.current_mg_kg

    def days_left(self, today: date) -> int:
        return (self.applies_from - today).days


def alerts_for(limits: LimitSource, ingredient: str, crop: str, market: str, today: date,
               horizon_days: int | None = None) -> list[Alert]:
    current = limit_on(limits, ingredient, crop, market, today)
    until = today + timedelta(days=horizon_days) if horizon_days is not None else None
    out = []
    for v in _distinct(upcoming(limits, ingredient, crop, market, today)):
        if until and v.applies_from > until:
            continue
        out.append(Alert(ingredient, crop, market, v.applies_from, current.value_mg_kg, v.value_mg_kg,
                         v.no_mrl_required, v.regulation, v.snapshot))
    return out


def alerts_for_program(program: Program, registry: RegistrySource, limits: LimitSource, today: date) -> list[Alert]:
    """Upcoming limits of every ingredient the program uses, marking the blocks harvested on or after the change."""
    used: dict[tuple[str, str], set[str]] = {}
    for app in program.applications:
        block = program.block(app.block)
        reg = registry.product(app.product_id)
        if block is None or reg is None:
            continue
        for ing in reg.ingredients:
            for market in block.markets:
                used.setdefault((ing, market), set()).add(block.key)
    out = []
    for (ing, market), blocks in sorted(used.items()):
        for a in alerts_for(limits, ing, program.crop, market, today):
            hit = tuple(sorted(b for b in blocks if program.block(b).harvest_on >= a.applies_from))
            out.append(replace(a, blocks_affected=hit))
    return sorted(out, key=lambda a: (a.applies_from, a.ingredient, a.market))


def _distinct(versions: list[MrlRecord]) -> list[MrlRecord]:
    """The same new limit listed in two annexes is one change."""
    seen, out = set(), []
    for v in versions:
        key = (v.residue, v.applies_from, v.value_mg_kg, v.no_mrl_required)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
