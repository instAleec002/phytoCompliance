"""Consistency between the version chain built from dates and the status the EU publishes.

On the snapshot date, the versions in force by dates must be exactly the ones the EU marks "Applicable"; a version
the EU marks "No longer applicable" without an end date in its data is flagged ``end_date_unknown`` and excluded.
"""
from __future__ import annotations

from datetime import date

from .queries import in_force
from .records import GraphRecords


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def check_against_eu_status(rec: GraphRecords, snapshot_day: date) -> dict:
    day = snapshot_day.isoformat()
    report = {}
    crops = {e["to"] for e in rec.edges.get("FOR_CROP", [])}
    for crop in sorted(crops):
        keys = [e["from"] for e in rec.edges["FOR_CROP"] if e["to"] == crop and e["from"].startswith("EU:")]
        versions = {k: {p: _iso(v) for p, v in rec.nodes["MrlVersion"][k].items()} for k in keys}
        by_dates = {k for k, m in versions.items() if in_force(m, day)}
        by_eu = {k for k, m in versions.items() if m.get("applicability") == "Applicable"}
        report[crop] = {"in_force_by_dates": len(by_dates), "applicable_by_eu": len(by_eu),
                        "only_by_dates": sorted(by_dates - by_eu), "only_by_eu": sorted(by_eu - by_dates),
                        "end_date_unknown": sum(1 for m in versions.values() if m.get("end_date_unknown"))}
    return report
