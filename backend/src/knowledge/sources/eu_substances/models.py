"""An EU active substance with its acute reference dose."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ActiveSubstance(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    status: str | None
    arfd_mg_kg_bw: float | None
    arfd_status: str              # set, not_needed, not_set
    arfd_text: str | None
    arfd_source: str | None       # regulation or EFSA conclusion that set it
    micro_organism: bool = False
