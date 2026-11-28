"""Snapshot of the Codex MRLs for the commodities of ``config/codex_commodities.yaml``: the commodity tree, the
pesticide index and one page per commodity, each stored as served, plus the parsed MRLs."""
from __future__ import annotations

from datetime import date

from knowledge.snapshots.store import Snapshot

from .client import COMMODITIES_URL, INDEX_URL, CodexClient, commodity_url
from .parser import parse_commodities, parse_commodity_page, parse_pesticide_index

MINIMUM_PESTICIDES = 150      # a guard against a parser that reads little, not an expected count


class LayoutChanged(Exception):
    pass


def resolve(commodities: list, wanted: dict) -> dict[str, str]:
    """Codex code -> commodity id, failing when a configured code is missing or appears twice."""
    by_code: dict[str, list] = {}
    for c in commodities:
        if c.code:
            by_code.setdefault(c.code, []).append(c)
    codes = {item["code"] for levels in wanted.values() for item in levels}
    problems = {code: len(by_code.get(code, [])) for code in codes if len(by_code.get(code, [])) != 1}
    if problems:
        raise LayoutChanged(f"Codex codes not found exactly once in the commodity tree: {problems}")
    return {code: by_code[code][0].id for code in codes}


def file_name(code: str) -> str:
    return "commodity_" + code.replace(" ", "_") + ".html"


def take_snapshot(wanted: dict, client: CodexClient, day: date | None = None) -> Snapshot:
    snap = Snapshot(source="codex", day=day or date.today(), params={"commodities": wanted})
    tree = client.page(COMMODITIES_URL)
    snap.write_bytes("commodity_tree.html", tree.encode("utf-8"), COMMODITIES_URL)
    ids = resolve(parse_commodities(tree), wanted)
    index = client.page(INDEX_URL)
    snap.write_bytes("pesticide_index.html", index.encode("utf-8"), INDEX_URL)
    pesticides = parse_pesticide_index(index)
    if len(pesticides) < MINIMUM_PESTICIDES:
        raise LayoutChanged(f"Codex pesticide index with {len(pesticides)} entries")
    mrls = []
    for code, cid in sorted(ids.items()):
        page = client.page(commodity_url(cid))
        snap.write_bytes(file_name(code), page.encode("utf-8"), commodity_url(cid))
        mrls += parse_commodity_page(page, code)
    snap.counts = {"pesticides_in_index": len(pesticides), "commodities": len(ids), "mrls": len(mrls)}
    snap.write_json("mrls.json", [m.model_dump() for m in mrls], COMMODITIES_URL)
    snap.write_json("pesticides.json", pesticides, INDEX_URL)
    snap.close()
    return snap
