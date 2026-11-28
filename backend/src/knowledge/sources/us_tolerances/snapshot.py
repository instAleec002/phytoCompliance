"""Snapshot of 40 CFR Part 180: the XML as served for the eCFR date, plus the parsed sections, with checks that the
parser still understands the layout."""
from __future__ import annotations

from datetime import date

from knowledge.snapshots.store import Snapshot

from .client import EcfrClient
from .models import UsSection
from .parser import parse_part

PART_FILE = "part_180.xml"
# sections every edition keeps; if one goes missing or empty, the layout changed and the parser must be revised
ANCHORS = {"180.582": "tolerance", "180.449": "tolerance", "180.1011": "exemption", "180.1021": "exemption"}
MINIMUM_SECTIONS = 500


class LayoutChanged(Exception):
    pass


def check_sections(sections: list[UsSection]) -> dict:
    by_number = {s.number: s for s in sections}
    problems = [n for n, kind in ANCHORS.items()
                if n not in by_number or by_number[n].kind != kind
                or (kind == "tolerance" and not by_number[n].tolerances)]
    if problems or len(sections) < MINIMUM_SECTIONS:
        raise LayoutChanged(f"Part 180: {len(sections)} sections (minimum {MINIMUM_SECTIONS}); anchors wrong {problems}")
    return {"sections": len(sections), "tolerance_sections": sum(s.kind == "tolerance" for s in sections),
            "exemptions": sum(s.kind == "exemption" for s in sections),
            "tolerance_rows": sum(len(s.tolerances) for s in sections)}


def take_snapshot(client: EcfrClient, day: date | None = None) -> Snapshot:
    as_of = client.current_date()
    snap = Snapshot(source="us_tolerances", day=day or date.today(), params={"ecfr_up_to_date_as_of": as_of})
    path = snap.write_bytes(PART_FILE, client.part(as_of), client.part_url(as_of))
    sections = parse_part(path)
    snap.counts = check_sections(sections)
    snap.write_json("sections.json", [s.model_dump(mode="json") for s in sections], client.part_url(as_of))
    snap.close()
    return snap
