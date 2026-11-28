"""Records of the Codex pesticide residue database."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class CodexCommodity(_Record):
    id: str
    code: str | None              # "FB 0020"
    name: str
    tree_level: int
    item_type: str


class CodexMrl(_Record):
    commodity_code: str
    pesticide: str                # as on the page: "Cypermethrins (including alpha- and zeta- cypermethrin)"
    value_mg_kg: float | None
    value_text: str
    year: int | None              # year the Commission adopted it
    at_limit_of_determination: bool
    symbols: str | None
    notes: str | None
