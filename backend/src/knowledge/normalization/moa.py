"""Ingredients to their mode-of-action groups (FRAC, IRAC, HRAC), on the same keys as the residue normalization.

An ingredient may belong to groups of several schemes (sulphur: FRAC M02 and IRAC UN; tolfenpyrad: FRAC 39 and IRAC
21A). Groups are written "SCHEME:code" so that only groups of the same scheme are compared.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge.sources.moa.models import MoaEntry

from .ingredients import Aliases, ingredient_key

MOA_ALIASES_FILE = Path(__file__).resolve().parents[3] / "config" / "moa_aliases.yaml"


@dataclass(frozen=True)
class MoaAliases:
    to_entry: dict[str, tuple[str, ...]]
    not_classified: dict[str, str]
    listed_elsewhere: dict[str, tuple[str, str]]     # ingredient -> (group, where the committee lists it)

    @classmethod
    def load(cls, path: Path = MOA_ALIASES_FILE) -> MoaAliases:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        to_entry = {ingredient_key(k): tuple(ingredient_key(t) for t in ([v] if isinstance(v, str) else v))
                    for k, v in (data.get("to_entry") or {}).items()}
        reasons = {ingredient_key(k): str(v) for k, v in (data.get("not_classified") or {}).items()}
        elsewhere = {ingredient_key(k): (v["group"], v["cite"]) for k, v in (data.get("listed_elsewhere") or {}).items()}
        overlap = (set(to_entry) | set(elsewhere)) & set(reasons)
        if overlap:
            raise ValueError(f"moa aliases both mapped and declared unclassified: {sorted(overlap)}")
        return cls(to_entry, reasons, elsewhere)


class MoaIndex:
    def __init__(self, entries: list[MoaEntry], aliases: MoaAliases | None = None,
                 ingredient_aliases: Aliases | None = None):
        self.aliases = aliases or MoaAliases.load()
        self.ingredient_aliases = ingredient_aliases or Aliases.load()
        self.by_key: dict[str, set[MoaEntry]] = {}
        for e in entries:
            self.by_key.setdefault(ingredient_key(e.name), set()).add(e)

    def entries(self, ingredient: str) -> set[MoaEntry]:
        iso = self.ingredient_aliases.iso(ingredient)
        out: set[MoaEntry] = set()
        for key in self.aliases.to_entry.get(iso, (iso,)):
            out |= self.by_key.get(key, set())
        if iso in self.aliases.listed_elsewhere:
            group, cite = self.aliases.listed_elsewhere[iso]
            scheme, code = group.split(":", 1)
            out.add(MoaEntry(scheme=scheme, code=code, name=ingredient, group_name=cite))
        return out

    def groups(self, ingredient: str) -> set[str]:
        return {e.group for e in self.entries(ingredient)}

    def reason(self, ingredient: str) -> str | None:
        return self.aliases.not_classified.get(self.ingredient_aliases.iso(ingredient))

    def missing_targets(self) -> list[str]:
        return sorted(t for targets in self.aliases.to_entry.values() for t in targets if t not in self.by_key)
