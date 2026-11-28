"""Ingredients to Codex pesticide names, on the same keys as the EU normalization (``config/codex_aliases.yaml``)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .ingredients import Aliases, ingredient_key

CODEX_ALIASES_FILE = Path(__file__).resolve().parents[3] / "config" / "codex_aliases.yaml"


@dataclass(frozen=True)
class CodexAliases:
    to_pesticide: dict[str, str]

    @classmethod
    def load(cls, path: Path = CODEX_ALIASES_FILE) -> CodexAliases:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls({ingredient_key(k): ingredient_key(v) for k, v in (data.get("to_pesticide") or {}).items()})


class CodexIndex:
    def __init__(self, pesticides: list[str], aliases: CodexAliases | None = None,
                 ingredient_aliases: Aliases | None = None):
        self.aliases = aliases or CodexAliases.load()
        self.ingredient_aliases = ingredient_aliases or Aliases.load()
        self.names = {ingredient_key(p): p for p in pesticides}

    def key(self, ingredient: str) -> str | None:
        """Key of the Codex pesticide for an ingredient, or None when the Codex has no MRL for it."""
        iso = self.ingredient_aliases.iso(ingredient)
        key = self.aliases.to_pesticide.get(iso, iso)
        return key if key in self.names else None

    def missing_targets(self) -> list[str]:
        return sorted(t for t in self.aliases.to_pesticide.values() if t not in self.names)
