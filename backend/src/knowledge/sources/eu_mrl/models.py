"""Records of the EU Pesticides Database (maximum residue levels and the products they apply to)."""
from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Applicability(str, Enum):
    APPLICABLE = "Applicable"
    NO_LONGER = "No longer applicable"
    NOT_YET = "Not yet applicable"


class MrlVersion(BaseModel):
    """One version of the limit of one residue in one product. Versions are never overwritten: a new regulation
    adds a version, the previous one stops applying, and both stay linked."""

    model_config = ConfigDict(frozen=True)

    residue_id: int
    residue_name: str | None
    product_id: int
    product_code: str | None
    product_name: str | None
    value_mg_kg: float | None
    value_text: str
    at_limit_of_determination: bool
    no_mrl_required: bool  # Annex IV: exempt from a limit, which is not the same as having no specific limit
    regulation: str
    regulation_url: str | None
    annex: str | None
    voted_on: date | None
    in_force_on: date | None
    applies_from: date | None
    applicability: Applicability
    version: int | None
    original_residue_id: int | None
    next_residue_id: int | None
    footnote: str | None

    def applies_on(self, day: date) -> bool:
        """Whether this version is the one in force on a given day (ignoring later versions)."""
        return self.applies_from is not None and self.applies_from <= day


class EuProduct(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: int
    parent_id: int | None
    code: str
    name: str
    scientific_names: list[str]
