"""Snapshot of the three classifications: the files as downloaded plus the parsed entries, with checks that the
parsers still understand the layout (anchors every edition keeps, and a minimum size)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from knowledge.snapshots.store import Snapshot

from .client import MoaClient
from .frac import parse_frac
from .hrac import parse_hrac
from .irac import parse_irac
from .models import MoaEntry

PARSERS = {"FRAC": parse_frac, "IRAC": parse_irac, "HRAC": parse_hrac}

# entries every edition keeps; if one is missing, the layout changed and the parser must be revised
ANCHORS = {"FRAC": {("pyraclostrobin", "11"), ("fludioxonil", "12"), ("sulphur", "M02"), ("boscalid", "7")},
           "IRAC": {("Abamectin", "6"), ("Acetamiprid", "4A"), ("Spinosad", "5"), ("Bifenthrin", "3A")},
           "HRAC": {("2,4-D", "4"), ("Glyphosate", "9")}}
# a guard against a parser that silently reads little, not an expected count (editions add and drop entries)
MINIMUM = {"FRAC": 200, "IRAC": 250, "HRAC": 250}


class LayoutChanged(Exception):
    pass


def check_entries(scheme: str, entries: list[MoaEntry]) -> dict:
    found = {(e.name, e.code) for e in entries}
    missing = sorted(a for a in ANCHORS[scheme] if a not in found)
    if missing or len(entries) < MINIMUM[scheme]:
        raise LayoutChanged(f"{scheme}: {len(entries)} entries (minimum {MINIMUM[scheme]}), anchors missing {missing}")
    return {"entries": len(entries), "groups": len({e.code for e in entries})}


def file_name(scheme: str, kind: str) -> str:
    return f"{scheme.lower()}.{kind}"


def parse_folder(folder: Path, sources: dict) -> list[MoaEntry]:
    out: list[MoaEntry] = []
    for scheme, src in sources.items():
        out += PARSERS[scheme](folder / file_name(scheme, src["kind"]))
    return out


def take_snapshot(sources: dict, client: MoaClient, day: date | None = None) -> Snapshot:
    snap = Snapshot(source="moa", day=day or date.today(),
                    params={k: {"edition": v["edition"], "url": v["url"]} for k, v in sources.items()})
    for scheme, src in sources.items():
        path = snap.write_bytes(file_name(scheme, src["kind"]), client.download(src["url"], src["kind"]), src["url"])
        entries = PARSERS[scheme](path)
        snap.counts[scheme] = check_entries(scheme, entries)
        snap.write_json(f"{scheme.lower()}_entries.json", [e.model_dump() for e in entries], src["url"])
    snap.close()
    return snap
