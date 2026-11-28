"""Consumption data for the acute intake of one commodity and population (EFSA PRIMo revision 3.1)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AcuteConsumption(BaseModel):
    model_config = ConfigDict(frozen=True)

    commodity_code: int           # EU code without the leading zero
    commodity: str
    population: str               # children or adults
    diet: str                     # most critical diet: "NL child"
    percentile: str
    lp_g_kg_bw: float             # large portion, g per kg body weight
    bw_kg: float
    lp_g_person: float
    unit_edible_g: float | None   # None with unit_below_25g
    unit_below_25g: bool
    case: str                     # "1", "2a", "2b"
    variability_factor: float
