"""Ingredients to EU active substances and their acute reference dose (``config/substance_aliases.yaml``)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge.sources.eu_substances.models import ActiveSubstance

from .ingredients import Aliases, ingredient_key

SUBSTANCE_ALIASES_FILE = Path(__file__).resolve().parents[3] / "config" / "substance_aliases.yaml"


@dataclass(frozen=True)
class SubstanceAliases:
    to_substance: dict[str, tuple[str, ...]]

    @classmethod
    def load(cls, path: Path = SUBSTANCE_ALIASES_FILE) -> SubstanceAliases:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls({ingredient_key(k): tuple(ingredient_key(t) for t in ([v] if isinstance(v, str) else v))
                    for k, v in (data.get("to_substance") or {}).items()})


@dataclass(frozen=True)
class ArfdRecord:
    value_mg_kg_bw: float | None
    status: str                   # set, not_needed, not_set
    source: str | None
    substances: tuple[str, ...]


class SubstanceIndex:
    def __init__(self, substances: list[ActiveSubstance], aliases: SubstanceAliases | None = None,
                 ingredient_aliases: Aliases | None = None):
        self.aliases = aliases or SubstanceAliases.load()
        self.ingredient_aliases = ingredient_aliases or Aliases.load()
        self.by_key: dict[str, list[ActiveSubstance]] = {}
        for s in substances:
            self.by_key.setdefault(ingredient_key(s.name), []).append(s)

    def substances(self, ingredient: str) -> list[ActiveSubstance]:
        iso = self.ingredient_aliases.iso(ingredient)
        return [s for key in self.aliases.to_substance.get(iso, (iso,)) for s in self.by_key.get(key, [])]

    def arfd(self, ingredient: str) -> ArfdRecord | None:
        found = self.substances(ingredient)
        if not found:
            return None
        names = tuple(sorted({s.name for s in found}))
        values = [s for s in found if s.arfd_status == "set"]
        if values:
            s = min(values, key=lambda s: s.arfd_mg_kg_bw)
            return ArfdRecord(s.arfd_mg_kg_bw, "set", s.arfd_source, names)
        if all(s.arfd_status == "not_needed" for s in found):
            return ArfdRecord(None, "not_needed", found[0].arfd_source, names)
        return ArfdRecord(None, "not_set", None, names)

    def missing_targets(self) -> list[str]:
        return sorted(t for targets in self.aliases.to_substance.values() for t in targets if t not in self.by_key)
