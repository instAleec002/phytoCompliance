"""Pre-harvest interval: the days SENASA sets between the last application of a product and the harvest.

The earliest safe harvest of a block is the latest ``applied_on + interval`` over its applications. A product whose
interval is not registered for that crop and pest leaves the date undetermined: it is reported, never assumed zero.
Only when SENASA notes that no interval applies (most biological products) may the harvest follow the application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from domain.ports import Registration, RegistrySource
from domain.validation.models import Application


@dataclass(frozen=True)
class IntervalCheck:
    application: Application
    interval_days: int | None
    safe_from: date | None          # first day the harvest may happen; None when the interval is unknown
    not_applicable: bool = False

    def met_on(self, harvest: date) -> bool | None:
        return None if self.safe_from is None else harvest >= self.safe_from


@dataclass(frozen=True)
class SafeHarvest:
    block: str
    safe_from: date | None
    limiting: Application | None     # the application that sets the date
    unknown: tuple[Application, ...] = field(default=())

    @property
    def determined(self) -> bool:
        return not self.unknown


def check(app: Application, crop: str, registry: RegistrySource) -> IntervalCheck:
    reg: Registration | None = registry.registration(app.product_id, crop, app.pest)
    if reg is None:
        return IntervalCheck(app, None, None)
    if reg.preharvest_interval_days is None and reg.preharvest_not_applicable:
        return IntervalCheck(app, None, app.applied_on, not_applicable=True)
    days = reg.preharvest_interval_days
    return IntervalCheck(app, days, None if days is None else app.applied_on + timedelta(days=days))


def safe_harvest(block: str, crop: str, applications: list[Application], registry: RegistrySource) -> SafeHarvest:
    checks = [check(a, crop, registry) for a in applications if a.block == block]
    known = [c for c in checks if c.safe_from is not None]
    unknown = tuple(c.application for c in checks if c.safe_from is None)
    if not known:
        return SafeHarvest(block, None, None, unknown)
    latest = max(known, key=lambda c: c.safe_from)
    return SafeHarvest(block, latest.safe_from, latest.application, unknown)
