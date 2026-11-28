"""Snapshot of EFSA PRIMo revision 3.1: the workbook as downloaded and the acute consumption rows of the crops."""
from __future__ import annotations

from datetime import date

from knowledge.snapshots.store import Snapshot
from knowledge.sources.moa.client import MoaClient

from .parser import parse_primo

FILE = "primo.xlsm"


class IncompleteData(Exception):
    pass


def take_snapshot(source: dict, codes: dict[str, int], client: MoaClient, day: date | None = None) -> Snapshot:
    """``codes``: crop key -> EU commodity code without the leading zero."""
    snap = Snapshot(source="primo", day=day or date.today(), params={**source, "codes": codes})
    path = snap.write_bytes(FILE, client.download(source["url"], "xlsx"), source["url"])
    rows = parse_primo(path, set(codes.values()))
    missing = sorted((crop, pop) for crop, code in codes.items() for pop in ("children", "adults")
                     if not any(r.commodity_code == code and r.population == pop for r in rows))
    if missing:
        raise IncompleteData(f"PRIMo without acute consumption for {missing}")
    snap.counts = {"rows": len(rows)}
    snap.write_json("acute_consumption.json", [r.model_dump() for r in rows], source["url"])
    snap.close()
    return snap
