"""Completeness checks for EU snapshots, so that incomplete data never goes unnoticed.

Findings of 27/10/2026 that motivated them:
- the bulk download was cut off by the server three times, at different sizes (83, 112 and 132 MB);
- the paged endpoint is complete: it ends when ``nextLink`` disappears, has no repeated rows, carries the same number
  of versions for every product, and every applicable limit has a residue name in the catalog. The same limit can
  appear twice when it is listed in Annex II and Annex III; that is legitimate, not a duplicate.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


class IncompleteData(RuntimeError):
    """Raised when a download or a page set is not complete."""


def exact_duplicates(items: list[dict]) -> int:
    counts = Counter(json.dumps(i, sort_keys=True) for i in items)
    return sum(c - 1 for c in counts.values() if c > 1)


def check_pages(items: list[dict]) -> dict:
    """A page set with repeated rows means pages overlapped, so rows may also be missing."""
    duplicates = exact_duplicates(items)
    if duplicates:
        raise IncompleteData(f"{duplicates} repeated rows: the pages overlapped")
    return {"rows": len(items), "exact_duplicates": 0}


def check_names(items: list[dict], catalog: list[dict]) -> dict:
    """Every limit that applies today must have a residue name."""
    names = {r["pesticide_residue_id"] for r in catalog}
    applicable = {i["pesticide_residue_id"] for i in items if i.get("applicability_text") == "Applicable"}
    missing = sorted(applicable - names)
    if missing:
        raise IncompleteData(f"{len(missing)} applicable residues without a name in the catalog: {missing[:10]}")
    return {"applicable_residues": len(applicable), "named": len(applicable)}


def check_same_structure(rows_per_product: dict[str, int]) -> dict:
    """The database lists every residue for every product, so all products should carry the same number of versions."""
    distinct = set(rows_per_product.values())
    if len(distinct) > 1:
        raise IncompleteData(f"products with different numbers of versions: {rows_per_product}")
    return {"versions_per_product": distinct.pop() if distinct else 0}


def check_ndjson_complete(path: Path) -> dict:
    """The last line of an NDJSON download must be a whole JSON object; otherwise the transfer was cut."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65536))
        tail = f.read().decode("utf-8", errors="replace").rstrip("\n").split("\n")[-1]
    try:
        json.loads(tail)
    except json.JSONDecodeError as exc:
        raise IncompleteData(f"download cut off at {size} bytes: last line is not a whole JSON object") from exc
    return {"bytes": size, "last_line_complete": True}
