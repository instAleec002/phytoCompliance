"""Buyer profiles: stricter limits that a retailer asks on top of the legal ones (``config/buyer_profiles/*.yaml``).

Each criterion is optional (``null`` means the buyer does not ask it):
- ``max_fraction_of_mrl_per_substance``: each residue below this fraction of its MRL;
- ``max_sum_of_mrl_fractions``: the sum of those fractions over all residues;
- ``max_number_of_residues``: residues detected in the lot;
- ``max_fraction_of_arfd``: dietary exposure against the acute reference dose (needs consumption data, not loaded).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BuyerProfile:
    key: str
    name: str
    max_fraction_of_mrl_per_substance: float | None = None
    max_sum_of_mrl_fractions: float | None = None
    max_number_of_residues: int | None = None
    max_fraction_of_arfd: float | None = None

    @classmethod
    def from_dict(cls, key: str, data: dict) -> BuyerProfile:
        fields = ("max_fraction_of_mrl_per_substance", "max_sum_of_mrl_fractions", "max_number_of_residues",
                  "max_fraction_of_arfd")
        unknown = set(data) - set(fields) - {"name"}
        if unknown:
            raise ValueError(f"profile {key}: unknown criteria {sorted(unknown)}")
        return cls(key=key, name=str(data.get("name") or key), **{f: data.get(f) for f in fields})


def load_profiles(folder: Path) -> dict[str, BuyerProfile]:
    return {p.stem: BuyerProfile.from_dict(p.stem, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
            for p in sorted(folder.glob("*.yaml"))}
