"""In-memory implementations of the domain ports, with figures taken from the real snapshots of 27/10/2026 (EU
product 46, blueberry) where a test depends on them."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from domain.compliance.models import MrlRecord
from domain.ports import IngredientInfo, Registration


def mrl(residue, value, applies_from, valid_until=None, regulation="Reg", **kw) -> MrlRecord:
    return MrlRecord(residue=residue, value_mg_kg=value, value_text=str(value), applies_from=applies_from,
                     valid_until=valid_until, regulation=regulation, snapshot="eu_mrl:2026-10-27", **kw)


PYRACLOSTROBIN = [
    mrl("Pyraclostrobin", 0.5, date(2008, 9, 1), date(2017, 4, 26), "Reg. (EC) 839/2008"),
    mrl("Pyraclostrobin", 4.0, date(2017, 4, 26), date(2017, 7, 11), "Reg. (EU) 2017/623"),
    mrl("Pyraclostrobin", 4.0, date(2017, 7, 11), date(2026, 2, 11), "Reg. (EU) 2017/1164"),
    mrl("Pyraclostrobin", 4.0, date(2026, 2, 11), None, "Commission Regulation (EU) 2026/140"),
]


@dataclass
class FakeLimits:
    versions_by: dict[tuple[str, str, str], list[MrlRecord]] = field(default_factory=dict)
    info_by: dict[tuple[str, str], IngredientInfo] = field(default_factory=dict)
    markets: set[str] = field(default_factory=lambda: {"EU"})

    def add(self, ingredient, versions, crop="blueberry", market="EU", **info) -> FakeLimits:
        self.versions_by[(ingredient, crop, market)] = list(versions)
        self.info_by[(ingredient, market)] = IngredientInfo(ingredient, tuple({v.residue for v in versions}), **info)
        return self

    def ingredient(self, ingredient, market):
        return self.info_by.get((ingredient, market), IngredientInfo(ingredient, ()))

    def versions(self, ingredient, crop, market):
        return list(self.versions_by.get((ingredient, crop, market), []))

    known: dict[str, date] = field(default_factory=dict)

    def loaded_markets(self):
        return set(self.markets)

    def known_from(self, market):
        return self.known.get(market)


@dataclass
class FakeRegistry:
    products: dict[str, Registration] = field(default_factory=dict)
    registrations: dict[tuple[str, str, str | None], Registration] = field(default_factory=dict)

    def add(self, product_id, ingredients, phi, crop="blueberry", pest="000626", name=None, biological=False,
            phi_not_applicable=False):
        reg = Registration(product_id, name or product_id, f"PQUA N° {product_id}", tuple(ingredients), phi, None,
                           biological, "sigia:2026-10-27", phi_not_applicable)
        self.products[product_id] = reg
        self.registrations[(product_id, crop, pest)] = reg
        return self

    def registration(self, product_id, crop, pest=None):
        if pest is not None:
            return self.registrations.get((product_id, crop, pest))
        found = [r for (p, c, _), r in self.registrations.items() if p == product_id and c == crop]
        return found[0] if found else None

    def product(self, product_id):
        return self.products.get(product_id)


@dataclass
class FakeModeOfAction:
    by_ingredient: dict[str, set[str]] = field(default_factory=dict)

    def groups(self, ingredient):
        return set(self.by_ingredient.get(ingredient, set()))
