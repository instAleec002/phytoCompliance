"""Snapshot of the EU active substances (raw pages as served, plus the merged substances)."""
from __future__ import annotations

from datetime import date

from knowledge.snapshots.store import Snapshot
from knowledge.sources.eu_mrl.client import BASE, EuMrlClient

from .parser import parse_substances

URL = f"{BASE}/active-substances"
ANCHORS = {"Pyraclostrobin", "Emamectin", "Formetanate"}   # substances every download keeps, each with an ARfD


class IncompleteData(Exception):
    pass


def take_snapshot(client: EuMrlClient, day: date | None = None) -> Snapshot:
    snap = Snapshot(source="eu_substances", day=day or date.today(), params={"endpoint": "active-substances"})
    rows = client._paged(URL, {})
    snap.write_json("active_substances_raw.json", rows, URL)
    substances = parse_substances(rows)
    names = {s.name: s for s in substances}
    missing = sorted(a for a in ANCHORS if a not in names or names[a].arfd_status != "set")
    if missing:
        raise IncompleteData(f"active substances without anchors (or their ARfD): {missing}")
    snap.counts = {"rows": len(rows), "substances": len(substances),
                   "arfd_set": sum(s.arfd_status == "set" for s in substances),
                   "arfd_not_needed": sum(s.arfd_status == "not_needed" for s in substances)}
    snap.write_json("active_substances.json", [s.model_dump() for s in substances], URL)
    snap.close()
    return snap
