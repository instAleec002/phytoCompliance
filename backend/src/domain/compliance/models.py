"""Values the compliance rules work with. Every answer carries where it comes from (regulation, snapshot), so the API
and the assistant can cite it without producing any figure themselves."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class LimitStatus(str, Enum):
    SPECIFIC = "specific"            # a limit set for this residue and crop
    DEFAULT = "default"              # no specific limit: the market default applies (EU: 0.01 mg/kg)
    EXEMPT = "exempt"                # no limit required (EU Annex IV)
    NOT_PERMITTED = "not_permitted"  # the market has no default and no tolerance (e.g. United States)
    NO_REFERENCE = "no_reference"    # a reference standard (Codex) sets no limit: the importing country decides
    WITHOUT_VALUE = "without_value"  # the source lists the residue for the crop with no value; its footnote says why
    NO_DATA = "no_data"              # the source of this market is not loaded yet


@dataclass(frozen=True)
class MrlRecord:
    """One version of a limit, as the data source gives it."""

    residue: str
    value_mg_kg: float | None
    value_text: str
    applies_from: date | None
    valid_until: date | None
    regulation: str
    annex: str | None = None
    at_limit_of_determination: bool = False
    no_mrl_required: bool = False
    end_date_unknown: bool = False
    applicability: str | None = None
    footnote: str | None = None
    snapshot: str | None = None
    history_known: bool = True       # False: the source gives only the state at its date (eCFR)

    def in_force_on(self, day: date) -> bool:
        if self.applies_from is None or self.applies_from > day or self.end_date_unknown:
            return False
        return self.valid_until is None or self.valid_until > day


@dataclass(frozen=True)
class Limit:
    """The answer to "which limit applies to this ingredient, in this crop and market, on this day"."""

    ingredient: str
    crop: str
    market: str
    day: date
    status: LimitStatus
    value_mg_kg: float | None
    at_limit_of_determination: bool
    regulation: str | None
    residue: str | None
    snapshot: str | None
    ambiguous: bool = False          # several EU residues could apply; the strictest is used
    note: str | None = None
    candidates: tuple[MrlRecord, ...] = field(default=(), repr=False)

    @property
    def any_detectable_residue_breaches(self) -> bool:
        """At the limit of determination (or the default), any residue the lab can detect is a breach."""
        return self.status is LimitStatus.DEFAULT or (self.status is LimitStatus.SPECIFIC and self.at_limit_of_determination)
