"""The domain ports (``domain.ports``) implemented over the AGE graph.

Ingredient names are normalized with the same aliases the loader used, so "AZUFRE" and "sulphur" reach the same node.
Mode-of-action groups come from the FRAC, IRAC and HRAC lists (:class:`GraphModeOfAction`).
"""
from __future__ import annotations

from datetime import date

from domain.compliance.models import MrlRecord
from domain.ports import AcuteIntakeData, Arfd, IngredientInfo, Registration
from knowledge.normalization.ingredients import Aliases
from knowledge.normalization.us import UsAliases

from .age import AgeGraph
from .queries import mrl_versions


def _day(value) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value else None


def to_record(m: dict) -> MrlRecord:
    return MrlRecord(residue=m.get("residue") or "", value_mg_kg=m.get("value_mg_kg"), value_text=m.get("value_text") or "",
                     applies_from=_day(m.get("applies_from")), valid_until=_day(m.get("valid_until")),
                     regulation=m.get("regulation") or "", annex=m.get("annex"),
                     at_limit_of_determination=bool(m.get("at_limit_of_determination")),
                     no_mrl_required=bool(m.get("no_mrl_required")), end_date_unknown=bool(m.get("end_date_unknown")),
                     applicability=m.get("applicability"), footnote=m.get("footnote"), snapshot=m.get("snapshot"),
                     history_known=m.get("history_known", True))


class GraphRepository:
    """:class:`domain.ports.LimitSource` and :class:`domain.ports.RegistrySource` over the graph."""

    def __init__(self, graph: AgeGraph, aliases: Aliases | None = None):
        self.graph = graph
        self.aliases = aliases or Aliases.load()
        self._markets: set[str] | None = None
        self.us_aliases = UsAliases.load()

    def key(self, ingredient: str) -> str:
        return self.aliases.iso(ingredient)

    # LimitSource
    def known_from(self, market: str) -> date | None:
        rows = self.graph.run("MATCH (m:Market {key: $market}) RETURN m.known_from", {"market": market})
        return _day(rows[0][0]) if rows and rows[0][0] else None

    def loaded_markets(self) -> set[str]:
        if self._markets is None:
            rows = self.graph.run("MATCH (:MrlVersion)-[:IN_MARKET]->(k:Market) RETURN DISTINCT k.key")
            self._markets = {r[0] for r in rows}
        return self._markets

    def ingredient(self, ingredient: str, market: str) -> IngredientInfo:
        """Residues of this market only (their keys start with the market), and the absence reason documented for it."""
        key = self.key(ingredient)
        rows = self.graph.run(
            "MATCH (i:Ingredient {key: $key}) OPTIONAL MATCH (i)-[:MEASURED_AS]->(r:Residue) "
            "RETURN i.biological, collect([r.key, r.name_en])", {"key": key}, columns=("bio", "residues"))
        biological, residues = (rows[0] if rows else (None, []))
        names = sorted(name for rkey, name in residues if rkey and name and rkey.startswith(f"{market}:"))
        return IngredientInfo(key, tuple(names), bool(biological), self._absence(key, market))

    def _absence(self, key: str, market: str) -> str | None:
        if market == "EU":
            return self.aliases.not_in_eu.get(key)
        if market == "US":
            return self.us_aliases.checked_absent.get(key)
        return None

    def versions(self, ingredient: str, crop: str, market: str) -> list[MrlRecord]:
        return [to_record(m) for m in mrl_versions(self.graph, self.key(ingredient), crop, market)]

    # RegistrySource
    def registration(self, product_id: str, crop: str, pest: str | None = None) -> Registration | None:
        """Without a pest, the longest pre-harvest interval among the authorizations of the product in the crop
        (the conservative one)."""
        pest_filter = ", (a)-[:AGAINST]->(:Pest {key: $pest})" if pest else ""
        rows = self.graph.run(
            "MATCH (a:Authorization)-[:OF_PRODUCT]->(p:Product {key: $product}), (a)-[:ON_CROP]->(:Crop {key: $crop})"
            f"{pest_filter} RETURN properties(p), a.preharvest_interval_days, a.peru_mrl_mg_kg, a.preharvest_not_applicable",
            {"product": product_id, "crop": crop, "pest": pest}, columns=("p", "phi", "mrl", "na"))
        if not rows:
            return None
        phis = [r[1] for r in rows if r[1] is not None]
        not_applicable = [bool(r[3]) for r in rows if r[1] is None]
        # one authorization with an unknown interval leaves it unknown; "not applicable" only if every one says so
        phi = max(phis) if phis and not not_applicable else None
        mrls = [r[2] for r in rows if r[2] is not None]
        return self._registration(rows[0][0], phi, min(mrls) if mrls else None,
                                  not_applicable=bool(not_applicable) and all(not_applicable) and not phis)

    def product(self, product_id: str) -> Registration | None:
        rows = self.graph.run("MATCH (p:Product {key: $product}) RETURN properties(p)", {"product": product_id})
        return self._registration(rows[0][0], None, None) if rows else None

    def _registration(self, props: dict, phi, peru_mrl, not_applicable: bool = False) -> Registration:
        rows = self.graph.run("MATCH (:Product {key: $product})-[:CONTAINS]->(i:Ingredient) RETURN i.key, i.biological",
                              {"product": props["key"]}, columns=("key", "bio"))
        return Registration(product_id=props["key"], trade_name=props.get("trade_name") or props["key"],
                            registration_number=props.get("registration_number"),
                            ingredients=tuple(sorted(r[0] for r in rows)), preharvest_interval_days=phi,
                            peru_mrl_mg_kg=peru_mrl, biological=bool(rows) and all(r[1] for r in rows),
                            snapshot=props.get("snapshot"), preharvest_not_applicable=not_applicable)


class GraphToxicology:
    """:class:`domain.ports.ToxicologySource` over the Ingredient and Crop properties."""

    def __init__(self, graph: AgeGraph, aliases: Aliases | None = None):
        self.graph = graph
        self.aliases = aliases or Aliases.load()

    def arfd(self, ingredient: str) -> Arfd | None:
        rows = self.graph.run("MATCH (i:Ingredient {key: $key}) RETURN i.arfd_mg_kg_bw, i.arfd_status, i.arfd_source",
                              {"key": self.aliases.iso(ingredient)}, columns=("v", "s", "src"))
        if not rows or rows[0][1] is None:
            return None
        value, status, source = rows[0]
        return Arfd(value, status, source)

    def acute_consumption(self, crop: str) -> list[AcuteIntakeData]:
        rows = self.graph.run("MATCH (c:Crop {key: $crop}) RETURN c.acute_consumption", {"crop": crop})
        if not rows or not rows[0][0]:
            return []
        return [AcuteIntakeData(commodity=r["commodity"], population=r["population"], diet=r["diet"],
                                lp_g_kg_bw=r["lp_g_kg_bw"], bw_kg=r["bw_kg"], lp_g_person=r["lp_g_person"],
                                unit_edible_g=r.get("unit_edible_g"), case=r["case"],
                                variability_factor=r["variability_factor"]) for r in rows[0][0]]


class GraphModeOfAction:
    """:class:`domain.ports.ModeOfActionSource` over the IN_GROUP edges (FRAC, IRAC and HRAC lists)."""

    def __init__(self, graph: AgeGraph, aliases: Aliases | None = None):
        self.graph = graph
        self.aliases = aliases or Aliases.load()

    def groups(self, ingredient: str) -> set[str]:
        rows = self.graph.run("MATCH (:Ingredient {key: $key})-[:IN_GROUP]->(g:MoaGroup) RETURN g.key",
                              {"key": self.aliases.iso(ingredient)})
        return {r[0] for r in rows}


class NoModeOfActionData:
    """:class:`domain.ports.ModeOfActionSource` for a graph loaded without the mode-of-action snapshot."""

    def groups(self, ingredient: str) -> set[str]:
        return set()
