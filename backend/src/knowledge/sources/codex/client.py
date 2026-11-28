"""Client for the Codex pesticide residue database pages (codex.fao.org). Polite pacing, retries, and a page is
accepted only when it is a whole HTML document (closing ``</html>``)."""
from __future__ import annotations

import time

import httpx

from knowledge.sources.sigia.client import USER_AGENT

BASE = "https://codex.fao.org/codex-texts/codex-online-databases/pesticides-residues"
COMMODITIES_URL = f"{BASE}/commodity-categories"
INDEX_URL = f"{BASE}/pesticide-index"


def commodity_url(commodity_id: str) -> str:
    return f"{COMMODITIES_URL}/commodities-details?commodityId={commodity_id}"


class IncompleteDownload(Exception):
    pass


class CodexClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, retries: int = 4, pause_s: float = 1.0,
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

    def page(self, url: str) -> str:
        last: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._http.get(url)
                response.raise_for_status()
                if "</html>" not in response.text[-2000:].lower():
                    raise IncompleteDownload("page without its closing </html>")
                if self._pause:
                    time.sleep(self._pause)
                return response.text
            except (httpx.HTTPError, IncompleteDownload) as e:
                last = e
                if attempt < self._retries and self._pause:
                    time.sleep(self._pause * attempt * 2)
        raise IncompleteDownload(f"{url}: {self._retries} attempts failed; last error: {last}")
