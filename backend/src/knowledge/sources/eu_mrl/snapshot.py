"""Dated snapshot of the EU limits for the crops in scope.

The paged ``pesticide-residues-mrls`` endpoint is the reference (see ``checks.py`` for why the bulk download is not
used). The snapshot pages each product, stores the residue catalog (names in English and Spanish) next to it, and
runs the completeness checks; if one fails, no manifest is written and the snapshot does not count.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from knowledge.snapshots.store import Snapshot

from .checks import check_names, check_pages, check_same_structure
from .client import BASE, EuMrlClient
from .parser import parse_mrl


def take_snapshot(product_codes: dict[str, str], client: EuMrlClient, day: date | None = None, root=None) -> Snapshot:
    """``product_codes`` maps a crop key to its EU product code, e.g. {"blueberry": "0154010"}."""
    snap = Snapshot(source="eu_mrl", day=day or date.today(), params={"product_codes": product_codes},
                    **({"root": root} if root else {}))
    catalog = client.residue_catalog()
    snap.write_json("residues_EN_ES.json", catalog, f"{BASE}/pesticide-residues")

    counts: dict = {"residues": len({r["pesticide_residue_id"] for r in catalog})}
    checks: dict = {}
    rows_per_product: dict[str, int] = {}
    for crop, code in product_codes.items():
        products = client.products(product_code=code)
        snap.write_json(f"product_{code}.json", products, f"{BASE}/pesticide-residues-products")
        if not products:
            raise ValueError(f"EU product code {code} ({crop}) not found")
        product_id = int(products[0]["product_id"])
        items = client.mrls(product_id)
        checks[crop] = {**check_pages(items), **check_names(items, catalog)}
        snap.write_json(f"mrls_{code}.json", items, f"{BASE}/pesticide-residues-mrls?product_id={product_id}")
        status = Counter(parse_mrl(i).applicability.value for i in items)
        counts[crop] = {"product_id": product_id, "mrl_versions": len(items), **status}
        rows_per_product[crop] = len(items)
    checks["all_products"] = check_same_structure(rows_per_product)

    snap.counts = counts
    snap.params["checks"] = checks
    snap.close()
    return snap
