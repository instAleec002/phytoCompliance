"""Download of the corpus into a dated snapshot, with one record per document.

``non_local/non_data/raw/corpus/<YYYY-MM-DD>/`` receives each file untouched plus ``manifest.json`` (files, hashes,
counts) and ``documents.json``: for every seed item its ``doc_id``, source, level, title, year, type, licence, origin
URL, file and status. An item that cannot enter (licence not accepted, restricted access, a type the source skips, no
usable file) is recorded as ``excluido`` with the reason, so the counter always explains the difference between the
seed and what was indexed.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx

from knowledge.snapshots.store import DATA_ROOT, Snapshot, sha256_of
from shared.settings import REPO

from .dspace import DSpaceClient
from .sources import Registry, SeedItem

SOURCE = "corpus"


@dataclass
class DocumentRecord:
    doc_id: str
    source: str
    level: str
    title: str
    year: str
    doc_type: str
    licence: str
    url: str
    file: str | None
    sha256: str | None
    bytes: int | None
    status: str                      # descargado | excluido
    reason: str = ""
    why: str = ""


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("_")[:90]


def _previous_downloads(base: Path, current: Path) -> dict[str, dict]:
    """doc_id -> record of its most recent successful download in an earlier snapshot whose file still exists."""
    found: dict[str, dict] = {}
    if not base.exists():
        return found
    # earlier snapshots first and the current one last, so a re-run on the same day reuses its own files too
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        doc = folder / "documents.json"
        if not doc.exists():
            continue
        for r in json.loads(doc.read_text(encoding="utf-8")):
            if r.get("status") == "descargado" and r.get("file") and (folder / r["file"]).exists():
                found[r["doc_id"]] = {**r, "_folder": str(folder)}
    return found


def doc_id_for(item: SeedItem) -> str:
    return f"{item.source}-{item.uuid[:8]}" if item.uuid else f"{item.source}-{Path(item.file).stem[:40]}"


def download_seed(registry: Registry, seed: list[SeedItem], day: date | None = None, root: Path = DATA_ROOT,
                  clients: dict[str, DSpaceClient] | None = None) -> tuple[Path, list[DocumentRecord]]:
    snap = Snapshot(SOURCE, day or date.today(), root=root, params={"seed": len(seed)})
    clients = dict(clients or {})
    records: list[DocumentRecord] = []
    refusals: dict[str, int] = {}
    previous = _previous_downloads(Path(root) / SOURCE, snap.folder)
    for item in seed:
        src = registry.sources[item.source]
        doc_id = doc_id_for(item)
        if src.kind == "local":
            path = REPO / src.folder / item.file
            name = f"{item.source}__{_safe(item.file)}"
            snap.folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, snap.folder / name)
            snap.register(name, f"local:{src.folder}/{item.file}")
            records.append(DocumentRecord(doc_id, item.source, src.level, Path(item.file).stem.replace("_", " "), "",
                                          "procedimiento interno", src.licence or "propio", f"local:{item.file}", name,
                                          sha256_of(snap.folder / name), (snap.folder / name).stat().st_size,
                                          "descargado", why=item.why))
            continue
        prev = previous.get(doc_id)
        if prev:   # already downloaded in an earlier snapshot: copy it instead of asking the repository again
            old = Path(prev["_folder"]) / prev["file"]
            snap.folder.mkdir(parents=True, exist_ok=True)
            if old.resolve() != (snap.folder / prev["file"]).resolve():
                shutil.copyfile(old, snap.folder / prev["file"])
            snap.register(prev["file"], f"reutilizado de {Path(prev['_folder']).name}: {prev['url']}")
            rec = DocumentRecord(**{k: v for k, v in prev.items() if not k.startswith("_")})
            records.append(rec)
            continue
        if not src.active:
            records.append(DocumentRecord(doc_id, item.source, src.level, "", "", "", "", "", None, None, None, "excluido",
                                          reason=f"fuente pausada: {src.paused_reason}", why=item.why))
            continue
        if refusals.get(item.source, 0) >= 3:
            records.append(DocumentRecord(doc_id, item.source, src.level, "", "", "", "", "", None, None, None, "excluido",
                                          reason="fuente no accesible (rechazó 3 pedidos seguidos)", why=item.why))
            continue
        client = clients.setdefault(item.source, DSpaceClient(src))
        try:
            remote = client.item(item.uuid)
            refusals[item.source] = 0
        except httpx.HTTPStatusError as e:
            refusals[item.source] = refusals.get(item.source, 0) + 1
            records.append(DocumentRecord(doc_id, item.source, src.level, "", "", "", "", "", None, None, None, "excluido",
                                          reason=f"fuente no accesible (HTTP {e.response.status_code})", why=item.why))
            continue
        url = f"{src.handle_url}{remote.handle}" if remote.handle and src.handle_url else client.api + f"/core/items/{item.uuid}"
        base = DocumentRecord(doc_id, item.source, src.level, remote.title, remote.year, remote.doc_type, remote.licence,
                              url, None, None, None, "excluido", why=item.why)
        if not registry.licence_ok(remote.licence):
            base.reason = f"licencia no aceptada: {remote.licence or 'sin licencia'}"
        elif any(a.lower() in (remote.access or "").lower() for a in src.skip_access):
            base.reason = f"acceso {remote.access}"
        elif remote.doc_type in src.skip_types:
            base.reason = f"tipo {remote.doc_type} excluido por la fuente"
        elif (f := client.main_file(remote)) is None:
            base.reason = "sin archivo PDF o DOCX utilizable"
        else:
            name = f"{item.source}__{item.uuid[:8]}__{_safe(f.name)}"
            try:
                data = client.download(f)
            except httpx.HTTPStatusError as e:
                # metadata can say open access while the file itself is embargoed or restricted
                base.reason = f"el archivo no se puede descargar (HTTP {e.response.status_code})"
                records.append(base)
                continue
            snap.write_bytes(name, data, f.content_url)
            entry = snap.files[-1]
            base.file, base.sha256, base.bytes, base.status = name, entry["sha256"], entry["bytes"], "descargado"
        records.append(base)
    snap.counts = {"items": len(records), "descargados": sum(r.status == "descargado" for r in records),
                   "excluidos": sum(r.status == "excluido" for r in records)}
    snap.write_json("documents.json", [asdict(r) for r in records], "derivado: registro de documentos")
    snap.close()
    return snap.folder, records
