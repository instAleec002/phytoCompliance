"""Active substances of the EU Pesticides Database (``active-substances``): status and toxicological reference values.

The endpoint repeats a substance once per linked residue and legislation; the toxicological values belong to the
substance, so rows are merged by ``substance_id`` and a substance whose ARfD differs between its rows stops the parse.
ARfD values come as "0.03 mg/kg bw", "Not appl." (EFSA judged an ARfD unnecessary) or empty (not set).
"""
from __future__ import annotations

import re

from .models import ActiveSubstance

_VALUE = re.compile(r"^\s*(\d*\.?\d+)\s*mg/kg\s*bw", re.IGNORECASE)


def parse_arfd(text: str | None) -> tuple[float | None, str]:
    """(value, status): status is "set", "not_needed" or "not_set"."""
    if not text or not text.strip():
        return None, "not_set"
    if m := _VALUE.match(text):
        return float(m.group(1)), "set"
    if text.strip().lower().startswith("not appl"):
        return None, "not_needed"
    return None, "not_set"


def parse_substances(rows: list[dict]) -> list[ActiveSubstance]:
    by_id: dict[int, ActiveSubstance] = {}
    for r in rows:
        value, status = parse_arfd(r.get("tox_value_arfd"))
        s = ActiveSubstance(id=int(r["substance_id"]), name=" ".join(str(r["substance_name"]).split()),
                            status=r.get("substance_status"), arfd_mg_kg_bw=value, arfd_status=status,
                            arfd_text=r.get("tox_value_arfd"),
                            arfd_source=r.get("tox_source_earfd") or r.get("tox_sourc_earfd"),
                            micro_organism=(r.get("as_micro_org") or "").lower() == "yes")
        seen = by_id.get(s.id)
        if seen and (seen.arfd_mg_kg_bw, seen.arfd_status) != (s.arfd_mg_kg_bw, s.arfd_status):
            raise ValueError(f"substance {s.id} ({s.name}) with two ARfD values: {seen.arfd_text} / {s.arfd_text}")
        by_id.setdefault(s.id, s)
    return sorted(by_id.values(), key=lambda s: s.id)
