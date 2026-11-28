"""eCFR API client for 40 CFR Part 180. The API serves the text as of a date; the client first asks which date the
title is current to, then downloads that version. The endpoint requires compressed responses. A download is accepted
only when the XML parses and contains the whole part, retrying a cut connection a few times."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import httpx

from knowledge.sources.sigia.client import USER_AGENT

BASE = "https://www.ecfr.gov/api/versioner/v1"


class IncompleteDownload(Exception):
    pass


def check_complete(data: bytes) -> None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise IncompleteDownload(f"Part 180 XML does not parse: {e}") from e
    if not any(d.get("N") == "180" for d in root.iter("DIV5")):
        raise IncompleteDownload("XML without the DIV5 of Part 180")


class EcfrClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, retries: int = 4, pause_s: float = 3.0,
                 timeout_s: float = 300.0):
        self._http = httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=True,
                                  headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        self._retries, self._pause = retries, pause_s

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def current_date(self, title: int = 40) -> str:
        response = self._http.get(f"{BASE}/titles.json")
        response.raise_for_status()
        entry = next(t for t in response.json()["titles"] if t["number"] == title)
        return entry["up_to_date_as_of"]

    def part_url(self, day: str, title: int = 40, part: str = "180") -> str:
        return f"{BASE}/full/{day}/title-{title}.xml?part={part}"

    def part(self, day: str, title: int = 40, part: str = "180") -> bytes:
        last: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                response = self._http.get(self.part_url(day, title, part))
                response.raise_for_status()
                check_complete(response.content)
                return response.content
            except (httpx.HTTPError, IncompleteDownload) as e:
                last = e
                if attempt < self._retries and self._pause:
                    time.sleep(self._pause * attempt)
        raise IncompleteDownload(f"Part {part}: {self._retries} attempts failed; last error: {last}")
