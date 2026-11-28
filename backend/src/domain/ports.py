"""What the domain needs from the data, as interfaces. ``knowledge.graph.repository`` implements them over the graph;
the tests implement them in memory. The domain never imports the language layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domain.compliance.models import MrlRecord


@dataclass(frozen=True)
class IngredientInfo:
    """How an ingredient is known to the limit sources of one market."""

    key: str
    residues: tuple[str, ...]        # residues the market sets limits for (empty: not in its catalog)
    biological: bool = False
    absence_reason: str | None = None


@dataclass(frozen=True)
class Registration:
    """A product registered in Peru for a crop and a pest."""

    product_id: str
    trade_name: str
    registration_number: str | None
    ingredients: tuple[str, ...]
    preharvest_interval_days: int | None
    peru_mrl_mg_kg: float | None
    biological: bool
    snapshot: str | None = None
    preharvest_not_applicable: bool = False   # SENASA notes that no interval applies (most biologicals)


@dataclass(frozen=True)
class Arfd:
    """Acute reference dose of the substance behind an ingredient."""

    value_mg_kg_bw: float | None
    status: str                      # set, not_needed (EFSA judged it unnecessary), not_set
    source: str | None = None


@dataclass(frozen=True)
class AcuteIntakeData:
    """Consumption of one commodity by one population for the acute intake (EFSA PRIMo)."""

    commodity: str
    population: str
    diet: str
    lp_g_kg_bw: float
    bw_kg: float
    lp_g_person: float
    unit_edible_g: float | None
    case: str
    variability_factor: float


class LimitSource(Protocol):
    def ingredient(self, ingredient: str, market: str) -> IngredientInfo: ...

    def versions(self, ingredient: str, crop: str, market: str) -> list[MrlRecord]: ...

    def loaded_markets(self) -> set[str]: ...

    def known_from(self, market: str) -> date | None:
        """First day whose state the source knows. None when it carries the full history (EU); the eCFR gives only the
        text in force at its date, so a US answer for an earlier day would be a guess."""
        ...


class RegistrySource(Protocol):
    def registration(self, product_id: str, crop: str, pest: str | None = None) -> Registration | None: ...

    def product(self, product_id: str) -> Registration | None: ...


class ToxicologySource(Protocol):
    def arfd(self, ingredient: str) -> Arfd | None: ...

    def acute_consumption(self, crop: str) -> list[AcuteIntakeData]: ...


class ModeOfActionSource(Protocol):
    def groups(self, ingredient: str) -> set[str]:
        """Groups as "SCHEME:code" ("FRAC:11", "IRAC:4A"); empty when no list classifies the ingredient."""
        ...
