"""Dated snapshots of official sources.

Every download is stored untouched under ``non_local/non_data/raw/<source>/<YYYY-MM-DD>/`` together with a
``manifest.json`` that records where it came from, when, with which parameters, and the SHA-256 of each file. The
graph and the rules always cite a snapshot, so any value can be traced back to the query that produced it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from shared.settings import REPO

DATA_ROOT = REPO / "non_local" / "non_data" / "raw"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Snapshot:
    """One dated download of a source. Files are added with :meth:`write_bytes`, :meth:`write_json` or
    :meth:`register`, and :meth:`close` writes the manifest."""

    source: str
    day: date
    root: Path = DATA_ROOT
    params: dict = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def folder(self) -> Path:
        return self.root / self.source / self.day.isoformat()

    def _path(self, name: str) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.folder / name

    def register(self, name: str, url: str) -> Path:
        """Record a file that was already written into the snapshot folder (e.g. a streamed download)."""
        path = self.folder / name
        self.files.append({"name": name, "url": url, "bytes": path.stat().st_size, "sha256": sha256_of(path)})
        return path

    def write_bytes(self, name: str, data: bytes, url: str) -> Path:
        path = self._path(name)
        path.write_bytes(data)
        return self.register(name, url)

    def write_json(self, name: str, obj, url: str) -> Path:
        return self.write_bytes(name, json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8"), url)

    def close(self) -> Path:
        manifest = {
            "source": self.source,
            "date": self.day.isoformat(),
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "params": self.params,
            "counts": self.counts,
            "files": self.files,
        }
        path = self._path("manifest.json")
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        return path


def latest(source: str, root: Path = DATA_ROOT) -> Path | None:
    """Folder of the most recent snapshot of a source, or None."""
    base = root / source
    if not base.exists():
        return None
    days = sorted(p for p in base.iterdir() if p.is_dir() and (p / "manifest.json").exists())
    return days[-1] if days else None
