"""Read-only catalog of the graph for the API: crops, markets, pests of a crop and the products registered for them."""
from __future__ import annotations

from .age import AgeGraph


class GraphCatalog:
    def __init__(self, graph: AgeGraph):
        self.graph = graph

    def crops(self) -> list[dict]:
        rows = self.graph.run("MATCH (c:Crop) RETURN properties(c)")
        keep = ("key", "name_es", "scientific_name", "eu_code", "us_crop_group", "sigia_id")
        return sorted(({k: r[0].get(k) for k in keep} for r in rows), key=lambda c: c["key"])

    def markets(self) -> list[dict]:
        rows = self.graph.run("MATCH (m:Market) RETURN properties(m)")
        keep = ("key", "name", "source", "known_from")
        return sorted(({k: r[0].get(k) for k in keep} for r in rows), key=lambda m: m["key"])

    def pests(self, crop: str) -> list[dict]:
        rows = self.graph.run(
            "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(p:Pest) "
            "RETURN p.key, p.scientific_name, p.common_name, p.other_use, count(a)",
            {"crop": crop}, columns=("key", "sci", "common", "other", "n"))
        return sorted(({"key": k, "scientific_name": s, "common_name": c, "other_use": bool(o), "products": n}
                       for k, s, c, o, n in rows), key=lambda p: (p["other_use"], p["common_name"] or ""))

    def products(self, crop: str, pest: str) -> list[dict]:
        rows = self.graph.run(
            "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(:Pest {key: $pest}), "
            "(a)-[:OF_PRODUCT]->(p:Product) OPTIONAL MATCH (p)-[:CONTAINS]->(i:Ingredient) "
            "RETURN p.key, p.trade_name, p.registration_number, p.product_type, a.preharvest_interval_days, "
            "a.preharvest_not_applicable, a.peru_mrl_mg_kg, a.snapshot, collect(i.key)",
            {"crop": crop, "pest": pest},
            columns=("id", "name", "reg", "type", "phi", "na", "mrl", "snap", "ingredients"))
        return sorted(({"product_id": i, "trade_name": n, "registration_number": r, "product_type": t,
                        "preharvest_interval_days": phi, "preharvest_not_applicable": bool(na), "peru_mrl_mg_kg": m,
                        "ingredients": sorted(ing), "snapshot": s}
                       for i, n, r, t, phi, na, m, s, ing in rows), key=lambda p: p["trade_name"] or "")

    def ingredients(self, crop: str | None = None, query: str | None = None, limit: int = 50) -> list[dict]:
        """Ingredients for autocomplete: those of the products registered for ``crop`` (or all), whose key contains
        ``query``; with the markets whose residues they are measured as."""
        if crop:
            rows = self.graph.run(
                "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:OF_PRODUCT]->(:Product)"
                "-[:CONTAINS]->(i:Ingredient) OPTIONAL MATCH (i)-[:MEASURED_AS]->(r:Residue) "
                "RETURN i.key, i.biological, collect(DISTINCT r.key)", {"crop": crop}, columns=("k", "b", "r"))
        else:
            rows = self.graph.run("MATCH (i:Ingredient) OPTIONAL MATCH (i)-[:MEASURED_AS]->(r:Residue) "
                                  "RETURN i.key, i.biological, collect(DISTINCT r.key)", columns=("k", "b", "r"))
        q = (query or "").strip().lower()
        found = {}
        for key, bio, residues in rows:
            if q and q not in key:
                continue
            markets = sorted({r.split(":", 1)[0] for r in residues if r})
            found[key] = {"key": key, "biological": bool(bio), "markets": markets}
        ordered = sorted(found.values(), key=lambda i: (not i["key"].startswith(q), i["key"]))
        return ordered[:limit]
