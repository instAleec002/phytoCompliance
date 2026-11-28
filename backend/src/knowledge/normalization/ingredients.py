"""Normalization of active ingredient names, so that a SIGIA product and an EU residue meet on the same key.

Three steps:
1. ``ingredient_key``: mechanical cleanup (case, accents, EU footnote marks, residue definitions in parentheses,
   British and American spelling).
2. Aliases from ``config/ingredient_aliases.yaml``: Spanish names, salts and spelling mistakes found in SIGIA, and the
   ingredients the EU groups under one residue (e.g. every copper salt under "copper compounds").
3. ``ResidueIndex.match``: exact key against the EU catalog; what does not match is reported, never guessed.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

ALIASES_FILE = Path(__file__).resolve().parents[3] / "config" / "ingredient_aliases.yaml"

_FOOTNOTES = re.compile(r"\((?:\s*[A-Z+]{1,3}\s*)\)")          # (F) (R) (A) (+) (++)
_PARENS = re.compile(r"\([^()]*\)")
_SPACES = re.compile(r"\s+")
_SPELLING = [("sulfate", "sulphate"), ("sulfur", "sulphur"), ("aluminum", "aluminium"), ("sulfonyl", "sulphonyl")]


_HEAD_SPLITS = (":", " and ", " including ", ",")
# a comma between two digits is a locant ("1,4-dimethylnaphthalene"), not the end of the name
_LOCANT_SAFE_COMMA = re.compile(r"(?<!\d),|,(?!\d)")


def residue_head(key: str) -> str:
    """Leading name of an EU residue definition: 'spirotetramat and spirotetramat-enol' -> 'spirotetramat';
    'formetanate: sum of formetanate and its salts' -> 'formetanate'; 'cyanamide including salts' -> 'cyanamide'."""
    head = key
    for sep in _HEAD_SPLITS:
        head = _LOCANT_SAFE_COMMA.split(head)[0] if sep == "," else head.split(sep)[0]
    return head.strip()


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def ingredient_key(name: str) -> str:
    """'Pyraclostrobin (F)' -> 'pyraclostrobin'; 'Bifenthrin (sum of isomers)(F)' -> 'bifenthrin';
    'Fatty acids:  Octanoic acid (+)(++)' -> 'fatty acids: octanoic acid'."""
    text = strip_accents(str(name or ""))
    text = _FOOTNOTES.sub(" ", text)
    while _PARENS.search(text):
        text = _PARENS.sub(" ", text)
    text = text.split(" expressed as ")[0]
    text = _SPACES.sub(" ", text).strip().lower().strip(" ,;.")
    for american, british in _SPELLING:
        text = text.replace(american, british)
    return text


@dataclass(frozen=True)
class Aliases:
    to_iso: dict[str, str]        # SIGIA spellings -> ISO common name
    to_residue: dict[str, tuple[str, ...]]   # ISO name -> keys of the EU residues that may cover it
    not_in_eu: dict[str, str]     # ISO name -> why there is no EU residue (checked against the catalog)

    @classmethod
    def load(cls, path: Path = ALIASES_FILE) -> Aliases:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        to_iso = {ingredient_key(k): ingredient_key(v) for k, v in (data.get("to_iso") or {}).items()}
        # one target, or several when SIGIA does not say which (a species without its strain) or names a mixture
        to_residue = {ingredient_key(k): tuple(ingredient_key(t) for t in ([v] if isinstance(v, str) else v))
                      for k, v in (data.get("to_residue") or {}).items()}
        reasons = {ingredient_key(k): str(v) for k, v in (data.get("not_in_eu") or {}).items()}
        overlap = set(to_residue) & set(reasons)
        if overlap:
            raise ValueError(f"aliases both mapped and declared absent: {sorted(overlap)}")
        return cls(to_iso=to_iso, to_residue=to_residue, not_in_eu=reasons)

    def iso(self, name: str) -> str:
        key = ingredient_key(name)
        return self.to_iso.get(key, key)

    def residue_keys(self, name: str) -> tuple[str, ...]:
        iso = self.iso(name)
        return self.to_residue.get(iso, (iso,))


@dataclass
class Match:
    ingredient: str
    iso: str
    residue_ids: list[int]
    not_in_eu: str | None = None  # known absence from the EU catalog, with its reason

    @property
    def matched(self) -> bool:
        return bool(self.residue_ids)

    @property
    def ambiguous(self) -> bool:
        """More than one EU residue, e.g. mineral oil: the EU separates paraffin oils by CAS and SIGIA gives none."""
        return len(self.residue_ids) > 1


class ResidueIndex:
    """EU residues indexed by the key of their English name."""

    def __init__(self, catalog: list[dict], aliases: Aliases | None = None):
        self.aliases = aliases or Aliases.load()
        self.by_key: dict[str, set[int]] = {}
        self.by_head: dict[str, set[int]] = {}
        self.names: dict[int, str] = {}
        for row in catalog:
            if row.get("pesticide_residue_lg") != "EN":
                continue
            rid = int(row["pesticide_residue_id"])
            self.names[rid] = row["pesticide_residue_name"].strip()
            key = ingredient_key(row["pesticide_residue_name"])
            self.by_key.setdefault(key, set()).add(rid)
            self.by_head.setdefault(residue_head(key), set()).add(rid)

    def match(self, ingredient: str) -> Match:
        """Exact key first, then the leading name of the EU definition. Unmatched ingredients are returned empty, with
        the documented reason when the absence is known."""
        ids: set[int] = set()
        for key in self.aliases.residue_keys(ingredient):
            ids |= self.by_key.get(key) or self.by_head.get(key) or set()
        iso = self.aliases.iso(ingredient)
        return Match(ingredient=ingredient, iso=iso, residue_ids=sorted(ids),
                     not_in_eu=None if ids else self.aliases.not_in_eu.get(iso))

    def missing_targets(self) -> list[str]:
        """Alias targets that are not in the catalog, by full name or by the leading name of the definition."""
        return sorted(t for targets in self.aliases.to_residue.values() for t in targets if t not in self.by_key and t not in self.by_head)


def spanish_names(aliases: Aliases) -> dict[str, str]:
    """ISO name -> a Spanish spelling used in SIGIA (the shortest one), lower case; the ISO name when there is none."""
    out: dict[str, str] = {}
    for spelling, iso in aliases.to_iso.items():
        if spelling != iso and (iso not in out or len(spelling) < len(out[iso])):
            out[iso] = spelling
    return {k: v.lower() for k, v in out.items()}
