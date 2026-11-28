"""Ingredients to their sections of 40 CFR Part 180, on the same keys as the EU normalization.

Chemical ingredients match by name or through ``config/us_aliases.yaml``; one without a section must be listed there as
checked absent. A biological species also matches the strain-specific exemptions that start with its name
("bacillus subtilis" -> "Bacillus subtilis strain QST 713"), as SIGIA gives no strain.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge.sources.us_tolerances.models import UsSection

from .ingredients import Aliases, ingredient_key

US_ALIASES_FILE = Path(__file__).resolve().parents[3] / "config" / "us_aliases.yaml"


@dataclass(frozen=True)
class UsAliases:
    to_section: dict[str, tuple[str, ...]]
    checked_absent: dict[str, str]

    @classmethod
    def load(cls, path: Path = US_ALIASES_FILE) -> UsAliases:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        to_section = {ingredient_key(k): tuple(ingredient_key(t) for t in ([v] if isinstance(v, str) else v))
                      for k, v in (data.get("to_section") or {}).items()}
        absent = {ingredient_key(k): str(v) for k, v in (data.get("checked_absent") or {}).items()}
        overlap = set(to_section) & set(absent)
        if overlap:
            raise ValueError(f"US aliases both mapped and declared absent: {sorted(overlap)}")
        return cls(to_section, absent)


class UsIndex:
    def __init__(self, sections: list[UsSection], aliases: UsAliases | None = None,
                 ingredient_aliases: Aliases | None = None):
        self.aliases = aliases or UsAliases.load()
        self.ingredient_aliases = ingredient_aliases or Aliases.load()
        self.by_key: dict[str, list[UsSection]] = {}
        for s in sections:
            self.by_key.setdefault(ingredient_key(s.substance), []).append(s)

    def sections(self, ingredient: str, biological: bool = False) -> list[UsSection]:
        iso = self.ingredient_aliases.iso(ingredient)
        out: list[UsSection] = []
        for key in self.aliases.to_section.get(iso, (iso,)):
            out += self.by_key.get(key, [])
        if not out and biological and len(iso.split()) >= 2:
            prefix = iso + " "
            out = [s for k, group in self.by_key.items() if k.startswith(prefix)
                   for s in group if s.kind == "exemption"]
        return out

    def reason(self, ingredient: str) -> str | None:
        return self.aliases.checked_absent.get(self.ingredient_aliases.iso(ingredient))

    def missing_targets(self) -> list[str]:
        return sorted(t for targets in self.aliases.to_section.values() for t in targets if t not in self.by_key)
