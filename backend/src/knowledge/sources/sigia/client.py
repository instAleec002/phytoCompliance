"""Client for the public SIGIA query service of SENASA.

It is the same service the official web page uses (``SIGIAWeb/consultas``, POST with ``C`` and ``S``). It is not a
documented API, so every answer is stored as a dated snapshot and the client is kept small and polite: one request at a
time, a pause between requests and a clear user agent.
"""
from __future__ import annotations

import json
import time

import httpx

BASE_URL = "https://servicios.senasa.gob.pe/SIGIAWeb/consultas"
USER_AGENT = "TP202620505-tesis-UPC (consulta academica; u202118038@upc.edu.pe)"


class SigiaClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, pause_s: float = 1.0, timeout_s: float = 60.0):
        self._http = httpx.Client(transport=transport, timeout=timeout_s, headers={"User-Agent": USER_AGENT})
        self._pause = pause_s

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _query(self, **form) -> list[list]:
        response = self._http.post(BASE_URL, data=form)
        response.raise_for_status()
        if self._pause:
            time.sleep(self._pause)
        return json.loads(response.text)

    def crops(self, common_name: str = "", scientific_name: str = "") -> list[list]:
        """Crops whose common or scientific name contains the text (raw rows)."""
        return self._query(C="CULTIVO", S="GETLIST", nombrecomun=common_name, nombrecientifico=scientific_name)

    def pests(self, crop_id: str) -> list[list]:
        """Pests and other uses registered for a crop (raw rows)."""
        return self._query(C="CULTIVO", S="PLAGAGETLIST", cultivoid=crop_id)

    def products(self, crop_id: str, pest_ids: list[str], other_use_classes: list[str] | None = None) -> list[list]:
        """Authorized products for a crop and one or more pests or other uses (raw rows)."""
        return self._query(C="CULTIVO", S="PLAGAPRODUCTOGETLIST", cultivoid=crop_id, plagas=",".join(pest_ids),
                           idclaseotrouso=",".join(other_use_classes or []))
