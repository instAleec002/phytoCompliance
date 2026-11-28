"""Client for the EU Pesticides Database API (DG SANTE data lake, version 3.0).

Official documentation: Pesticides-APIs-V3.0.pdf (api.datalake.sante.service.ec.europa.eu/files/download).
Observed on 27/10/2026, different from the manual:
- the bulk download asks for ``language_code`` (the manual says ``language``);
- ``pesticide-residues`` fails with ``language`` and, without it, returns one row per language, so the client filters
  by ``pesticide_residue_lg``.
Paged endpoints continue with the ``nextLink`` of each answer.
"""
from __future__ import annotations

from pathlib import Path

import httpx

BASE = "https://api.datalake.sante.service.ec.europa.eu/sante/pesticides"
VERSION = "v3.0"
USER_AGENT = "TP202620505-tesis-UPC (consulta academica; u202118038@upc.edu.pe)"


class EuMrlClient:
    def __init__(self, transport: httpx.BaseTransport | None = None, timeout_s: float = 120.0):
        self._http = httpx.Client(transport=transport, timeout=timeout_s, headers={"User-Agent": USER_AGENT},
                                  follow_redirects=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _paged(self, url: str, params: dict) -> list[dict]:
        items, next_url, next_params = [], url, {**params, "format": "json", "api-version": VERSION}
        while next_url:
            response = self._http.get(next_url, params=next_params)
            response.raise_for_status()
            payload = response.json()
            items += payload.get("value", [])
            next_url, next_params = payload.get("nextLink"), None
        return items

    def products(self, product_id: int | None = None, product_code: str | None = None, language: str = "EN") -> list[dict]:
        params = {"language": language}
        if product_id is not None:
            params["product_id"] = product_id
        if product_code:
            params["product_code"] = product_code
        return self._paged(f"{BASE}/pesticide-residues-products", params)

    def mrls(self, product_id: int) -> list[dict]:
        """Every version of every limit for one product (raw items)."""
        return self._paged(f"{BASE}/pesticide-residues-mrls", {"product_id": product_id})

    def residue_names(self, residue_id: int, languages: tuple[str, ...] = ("EN", "ES")) -> dict[str, str]:
        rows = self._paged(f"{BASE}/pesticide-residues", {"pesticide_residue_id": residue_id})
        return {r["pesticide_residue_lg"]: r["pesticide_residue_name"] for r in rows if r["pesticide_residue_lg"] in languages}

    def residue_catalog(self, languages: tuple[str, ...] = ("EN", "ES")) -> list[dict]:
        """Every residue with its name and footnotes, only in the requested languages (the endpoint returns all 23)."""
        rows = self._paged(f"{BASE}/pesticide-residues", {})
        return [r for r in rows if r["pesticide_residue_lg"] in languages]

    def download_all(self, destination: Path, language_code: str = "EN") -> str:
        """Streams the bulk download (NDJSON) into a file and returns the URL used. About 80 MB.

        Not used for snapshots: on 27/10/2026 the server cut it off three times at different sizes (83, 112 and
        132 MB). The file is checked after the transfer and an IncompleteData error is raised if it was cut."""
        url = f"{BASE}/pesticide-residues-mrls-download"
        params = {"language_code": language_code, "format": "json", "api-version": VERSION}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._http.stream("GET", url, params=params) as response:
            response.raise_for_status()
            with destination.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        from .checks import check_ndjson_complete
        check_ndjson_complete(destination)
        return str(httpx.URL(url, params=params))
