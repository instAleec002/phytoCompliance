"""Read-only query templates over the graph. The domain rules and the API use these; generated Cypher never replaces
them for the exact checks."""
from __future__ import annotations

from datetime import date

from .age import AgeGraph


def mrl_versions(graph: AgeGraph, ingredient: str, crop: str, market: str = "EU") -> list[dict]:
    """Every version of the limits that apply to an ingredient in a crop and market, newest first."""
    rows = graph.run(
        "MATCH (i:Ingredient {key: $ingredient})-[:MEASURED_AS]->(r:Residue)<-[:OF_RESIDUE]-(m:MrlVersion)"
        "-[:FOR_CROP]->(:Crop {key: $crop}), (m)-[:IN_MARKET]->(:Market {key: $market}) "
        "RETURN properties(m), r.name_en",
        {"ingredient": ingredient, "crop": crop, "market": market}, columns=("mrl", "residue"))
    out = [{**props, "residue": residue} for props, residue in rows]
    return sorted(out, key=lambda m: m.get("applies_from") or "", reverse=True)


def in_force(m: dict, day: str) -> bool:
    """Whether a version applies on ``day`` (ISO date): from its application date until it is replaced. Versions whose
    end date is unknown are excluded; the caller sees them flagged in :func:`mrl_versions`."""
    if not m.get("applies_from") or m["applies_from"] > day or m.get("end_date_unknown"):
        return False
    return not m.get("valid_until") or m["valid_until"] > day


def mrl_on(graph: AgeGraph, ingredient: str, crop: str, day: date, market: str = "EU") -> list[dict]:
    """Limits in force on a given day. A version marked "Not yet applicable" counts from its application date."""
    iso = day.isoformat()
    return [m for m in mrl_versions(graph, ingredient, crop, market) if in_force(m, iso)]


def authorized_products(graph: AgeGraph, crop: str, pest: str) -> list[dict]:
    """Products registered in Peru for a crop and a pest, with their ingredients and pre-harvest interval."""
    rows = graph.run(
        "MATCH (a:Authorization)-[:ON_CROP]->(:Crop {key: $crop}), (a)-[:AGAINST]->(:Pest {key: $pest}), "
        "(a)-[:OF_PRODUCT]->(p:Product) OPTIONAL MATCH (p)-[:CONTAINS]->(i:Ingredient) "
        "RETURN p.trade_name, p.registration_number, p.product_type, a.preharvest_interval_days, collect(i.key)",
        {"crop": crop, "pest": pest}, columns=("name", "registration", "type", "phi", "ingredients"))
    return [dict(zip(("trade_name", "registration_number", "product_type", "preharvest_interval_days", "ingredients"), r))
            for r in rows]
