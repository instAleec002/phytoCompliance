"""Client for DSpace 7 repositories (INIA, SENASA and UNALM use it). Reads an item's metadata and its ORIGINAL files
and downloads one. File URLs are built from bundle and bitstream ids when the source says so, because some servers
publish HAL links without their ``/server`` prefix (INIA)."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .sources import Source

HEADERS = {"Accept": "application/json", "User-Agent": "TP202620505-corpus (tesis UPC)"}


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int | None
    uuid: str
    content_url: str


@dataclass(frozen=True)
class RemoteItem:
    uuid: str
    handle: str | None
    title: str
    year: str
    doc_type: str
    licence: str
    access: str
    language: str
    files: tuple[RemoteFile, ...]


def _meta(item: dict, key: str) -> str:
    vals = item.get("metadata", {}).get(key) or []
    return vals[0]["value"] if vals else ""


class DSpaceClient:
    def __init__(self, source: Source, client: httpx.Client | None = None, pause_s: float = 1.0):
        self.source = source
        self.api = source.api.rstrip("/")
        self.http = client or httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True)
        self.pause_s = pause_s

    def _get(self, url: str) -> dict:
        for attempt in range(3):
            r = self.http.get(url)
            if r.status_code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(self.pause_s)
            return r.json()
        raise RuntimeError(f"sin respuesta de {url}")

    def item(self, uuid: str) -> RemoteItem:
        it = self._get(f"{self.api}/core/items/{uuid}")
        bundles = self._get(f"{self.api}/core/items/{uuid}/bundles")["_embedded"]["bundles"]
        files: list[RemoteFile] = []
        for b in bundles:
            if b["name"] != "ORIGINAL":
                continue
            href = f"{self.api}/core/bundles/{b['uuid']}/bitstreams" if self.source.build_links \
                else b["_links"]["bitstreams"]["href"]
            for bs in self._get(href)["_embedded"]["bitstreams"]:
                files.append(RemoteFile(name=bs["name"], size=bs.get("sizeBytes"), uuid=bs["uuid"],
                                        content_url=f"{self.api}/core/bitstreams/{bs['uuid']}/content"))
        licence = _meta(it, "dc.rights.uri") or _meta(it, "dc.rights")
        return RemoteItem(uuid=uuid, handle=it.get("handle"), title=it.get("name", "").strip(),
                          year=_meta(it, "dc.date.issued")[:4], doc_type=_meta(it, "dc.type").rsplit("/", 1)[-1],
                          licence=licence, access=_meta(it, "dc.rights.accessRights") or _meta(it, "dc.rights"),
                          language=_meta(it, "dc.language.iso") or "spa", files=tuple(files))

    def main_file(self, item: RemoteItem) -> RemoteFile | None:
        """The document itself: a PDF or DOCX that the source does not skip (originality reports, forms, abstracts),
        the largest when several remain."""
        usable = [f for f in item.files if f.name.lower().endswith((".pdf", ".docx")) and not self.source.skips_file(f.name)]
        return max(usable, key=lambda f: f.size or 0, default=None)

    def download(self, f: RemoteFile) -> bytes:
        r = self.http.get(f.content_url, headers={"Accept": "*/*"})
        r.raise_for_status()
        time.sleep(self.pause_s)
        return r.content
