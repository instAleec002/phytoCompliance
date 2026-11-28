"""Dated snapshot of SIGIA for one crop: its pests and other uses, and the authorized products for each one.

Each crop has its own folder (``sigia/<crop id>/<date>/``) with its own manifest, so crops downloaded on the same day
do not overwrite each other and every crop keeps its latest download."""
from __future__ import annotations

from datetime import date

from knowledge.snapshots.store import Snapshot

from .client import BASE_URL, SigiaClient
from .parser import parse_pests, parse_products


def take_snapshot(crop_id: str, client: SigiaClient, day: date | None = None, root=None) -> Snapshot:
    snap = Snapshot(source=f"sigia/{crop_id}", day=day or date.today(), params={"crop_id": crop_id}, **({"root": root} if root else {}))
    pest_rows = client.pests(crop_id)
    snap.write_json(f"pests_{crop_id}.json", pest_rows, BASE_URL)
    pests = parse_pests(pest_rows)

    total = 0
    for pest in pests:
        key = pest.pest_id or f"use{pest.other_use_class}"
        rows = client.products(crop_id, [pest.pest_id or ""], [pest.other_use_class or ""])
        if rows:
            snap.write_json(f"products_{crop_id}_{key}.json", rows, BASE_URL)
            total += len(parse_products(rows))
    snap.counts = {"pests": sum(not p.is_other_use for p in pests), "other_uses": sum(p.is_other_use for p in pests),
                   "product_uses": total}
    snap.close()
    return snap
