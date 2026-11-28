"""Limit in force and upcoming limits."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from domain.compliance.models import Limit, MrlRecord


class LimitOut(BaseModel):
    ingredient: str
    crop: str
    market: str
    day: date
    status: str = Field(description="specific, default, exempt, not_permitted, no_reference, without_value o no_data")
    value_mg_kg: float | None
    at_limit_of_determination: bool
    regulation: str | None
    residue: str | None
    snapshot: str | None
    ambiguous: bool
    note: str | None

    @classmethod
    def of(cls, lim: Limit) -> LimitOut:
        return cls(ingredient=lim.ingredient, crop=lim.crop, market=lim.market, day=lim.day, status=lim.status.value,
                   value_mg_kg=lim.value_mg_kg, at_limit_of_determination=lim.at_limit_of_determination,
                   regulation=lim.regulation, residue=lim.residue, snapshot=lim.snapshot, ambiguous=lim.ambiguous,
                   note=lim.note)


class VersionOut(BaseModel):
    residue: str
    value_mg_kg: float | None
    value_text: str
    applies_from: date | None
    valid_until: date | None
    regulation: str
    no_mrl_required: bool
    footnote: str | None
    snapshot: str | None

    @classmethod
    def of(cls, v: MrlRecord) -> VersionOut:
        return cls(residue=v.residue, value_mg_kg=v.value_mg_kg, value_text=v.value_text, applies_from=v.applies_from,
                   valid_until=v.valid_until, regulation=v.regulation, no_mrl_required=v.no_mrl_required,
                   footnote=v.footnote, snapshot=v.snapshot)
