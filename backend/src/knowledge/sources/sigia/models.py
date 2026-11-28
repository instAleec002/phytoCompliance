"""Records of the SIGIA registry, already cleaned (trimmed names, numbers parsed, ranges split)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class Crop(_Record):
    crop_id: str
    scientific_name: str
    common_name: str


class Pest(_Record):
    """A pest of a crop, or an "other use" (e.g. foliar applications), which SIGIA lists in the same table with an
    empty pest id and a use-class code."""

    pest_id: str | None
    scientific_name: str
    common_name: str
    other_use_class: str | None

    @property
    def is_other_use(self) -> bool:
        return self.pest_id is None


class DoseRange(_Record):
    raw: str
    minimum: float | None
    maximum: float | None


class Product(_Record):
    """An authorized use: one product registered for one crop and one pest."""

    product_id: str
    trade_name: str
    holder_id: str
    holder_name: str
    registration_number: str
    active_ingredients: list[str]
    use_class: str
    toxicity: str | None
    crop_id: str
    pest_id: str
    crop_scientific_name: str
    pest_scientific_name: str
    crop_common_name: str
    pest_common_name: str
    dose_unit: str | None
    dose_per_hectare: DoseRange | None
    dose_percent: DoseRange | None
    tank_capacity_l: float | None
    dose_per_tank: DoseRange | None
    peru_mrl_mg_kg: float | None
    preharvest_interval_days: int | None
    preharvest_interval_not_applicable: bool = False  # SENASA notes that no interval applies (most biologicals)
    notes: str | None
    product_type: str  # QUIMICO or BIOLOGICO

    @property
    def is_biological(self) -> bool:
        return self.product_type.upper() == "BIOLOGICO"
