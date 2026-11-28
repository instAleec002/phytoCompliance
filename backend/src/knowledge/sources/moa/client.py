"""Downloads the classification files. Several retries with a growing pause, and a file is accepted only when it is
complete: a PDF must end with its ``%%EOF`` marker and an xlsx must be a whole zip archive. A cut connection fails
loudly instead of leaving half a file in a snapshot.
"""
from __future__ import annotations

import io
import time
import zipfile

import httpx

from knowledge.sources.sigia.client import USER_AGENT


class IncompleteDownload(Exception):
    pass


def check_complete(data: bytes, kind: str) -> None:
    if kind == "pdf":
        if not data.startswith(b"%PDF") or b"%%EOF" not in data[-2048:]:
            raise IncompleteDownload("PDF without its header or its %%EOF marker")
    elif kind == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                bad = z.testzip()
        except zipfile.BadZipFile as e:
            raise IncompleteDownload(f"xlsx is not a complete zip: {e}") from e
        if bad:
            raise IncompleteDownload(f"xlsx with a damaged member: {bad}")
    else:
        raise ValueError(f"unknown kind {kind}")


class MoaClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, retries: int = 4, pause_s: float = 3.0,
                 timeout_s: float = 120.0):
        self._http = httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=True,
                                  headers={"User-Agent": USER_AGENT})
        self._retries, self._pause = retries, pause_s

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def download(self, url: str, kind: str) -> bytes:
        last: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._http.get(url)
                response.raise_for_status()
                check_complete(response.content, kind)
                return response.content
            except (httpx.HTTPError, IncompleteDownload) as e:
                last = e
                if attempt < self._retries and self._pause:
                    time.sleep(self._pause * attempt)
        raise IncompleteDownload(f"{url}: {self._retries} attempts failed; last error: {last}")
