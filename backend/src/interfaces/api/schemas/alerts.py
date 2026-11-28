"""Early alerts for limits that apply later."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from domain.alerts.upcoming import Alert


class AlertOut(BaseModel):
    ingredient: str
    crop: str
    market: str
    applies_from: date
    days_left: int
    current_mg_kg: float | None
    new_mg_kg: float | None
    new_no_mrl_required: bool
    stricter: bool
    regulation: str
    snapshot: str | None
    blocks_affected: list[str]

    @classmethod
    def of(cls, a: Alert, today: date) -> AlertOut:
        return cls(ingredient=a.ingredient, crop=a.crop, market=a.market, applies_from=a.applies_from,
                   days_left=a.days_left(today), current_mg_kg=a.current_mg_kg, new_mg_kg=a.new_mg_kg,
                   new_no_mrl_required=a.new_no_mrl_required, stricter=a.stricter, regulation=a.regulation,
                   snapshot=a.snapshot, blocks_affected=list(a.blocks_affected))
