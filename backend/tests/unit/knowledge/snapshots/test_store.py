"""Snapshots: dated folder, manifest with SHA-256, and the latest snapshot of a source."""
import hashlib
import json
from datetime import date

from knowledge.snapshots.store import Snapshot, latest


def test_manifest_records_files_and_hashes(tmp_path):
    snap = Snapshot(source="sigia", day=date(2026, 10, 27), root=tmp_path, params={"crop_id": "023075"})
    snap.write_json("pests_023075.json", [["000626", "Botrytis cinerea", "Moho gris", "", ""]], "https://example.org")
    snap.counts = {"pests": 1}
    manifest = json.loads(snap.close().read_text(encoding="utf-8"))

    data = (tmp_path / "sigia" / "2026-10-27" / "pests_023075.json").read_bytes()
    assert manifest["date"] == "2026-10-27" and manifest["params"] == {"crop_id": "023075"}
    assert manifest["files"][0]["sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["counts"] == {"pests": 1}


def test_latest_picks_the_most_recent(tmp_path):
    for day in (date(2026, 9, 24), date(2026, 10, 27)):
        s = Snapshot(source="eu_mrl", day=day, root=tmp_path)
        s.write_bytes("x.json", b"{}", "https://example.org")
        s.close()
    assert latest("eu_mrl", root=tmp_path).name == "2026-10-27"
    assert latest("missing", root=tmp_path) is None
