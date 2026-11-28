"""Which commodity rows of 40 CFR 180 cover a crop (``config/us_commodities.yaml``).

A tolerance for a crop group or subgroup covers every crop the group lists in § 180.41 ("Bushberry subgroup 13-07B"
covers highbush blueberry). The names in Part 180 are not uniform ("Bushberrry", "13-7G", "subgroup13-07F"), so they
are normalized before the rules apply, and a row naming the crop after "except" is left out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

US_COMMODITIES_FILE = Path(__file__).resolve().parents[4] / "config" / "us_commodities.yaml"
_SPELLING = [(re.compile(r"bushberr+y"), "bushberry"), (re.compile(r"\b13-7([a-h])\b"), r"13-07\1"),
             (re.compile(r"subgroup(\d)"), r"subgroup \1"), (re.compile(r"\bsubgroups\b"), "subgroup"),
             (re.compile(r"low-growing"), "low growing"), (re.compile(r"kiwi fruit"), "kiwifruit")]


# a footnote marker printed after the commodity («Avocado 1», «Grape, table 2»); the eCFR footnote usually says the
# tolerance has no US registration. A trailing number after «group» or «subgroup» is the group code, not a footnote.
_NOTA = re.compile(r"^(.*?[a-z)])\s+\d{1,2}$")


def normalize(commodity: str) -> str:
    text = commodity.lower()
    m = _NOTA.match(text.strip())
    if m and not re.search(r"\b(?:sub)?groups?$", m.group(1)):
        text = m.group(1)            # 27/11/2026: 20 tolerances of the three crops were lost behind a footnote
    text = text.replace(",", " ").replace("(", " ").replace(")", " ")
    for pattern, repl in _SPELLING:
        text = pattern.sub(repl, text)
    return " ".join(text.split())


@dataclass(frozen=True)
class CropRule:
    crop: str
    names: tuple[str, ...]           # whole commodity names, normalized
    groups: tuple[str, ...]          # regex over the normalized name for groups and subgroups
    excluded_after_except: str       # regex: the crop named after "except"
    flags: dict[str, str]            # normalized name -> note (postharvest, imported)

    def covers(self, commodity: str) -> bool:
        text = normalize(commodity)
        head, _, tail = text.partition(" except ")
        if tail and re.search(self.excluded_after_except, tail):
            return False
        if text in self.names or head in self.names:
            return True
        return any(re.search(g, text) for g in self.groups)

    def note(self, commodity: str) -> str | None:
        return self.flags.get(normalize(commodity))


def load_rules(path: Path = US_COMMODITIES_FILE) -> dict[str, CropRule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {crop: CropRule(crop, tuple(normalize(n) for n in r.get("names", [])), tuple(r.get("groups", [])),
                           r["excluded_after_except"], {normalize(k): v for k, v in (r.get("flags") or {}).items()})
            for crop, r in data.items()}
