"""AGROVOC (FAO, CC BY 4.0) for the terms of the graph: crops, pests and active ingredients (stage 4, 11/11/2026).

For each graph term the public Skosmos REST API is searched (``/search``) and the concept is fetched (``/data``): its
preferred and alternative labels in Spanish, English and Latin, its broader concepts and its exact matches. Only exact
label matches are accepted (case and accents ignored), never the first fuzzy hit, so a term without a concept stays
without one. Requests are slow and identified (one every ``pause_s`` seconds); everything is saved as a dated snapshot
(source «agrovoc») so the vocabulary can be rebuilt offline."""
from __future__ import annotations

import time
import unicodedata
from datetime import date

import httpx

from knowledge.snapshots.store import DATA_ROOT, Snapshot

API = "https://agrovoc.fao.org/browse/rest/v1"
LANGS = ("es", "en", "la")
UA = "TP202620505-agrovoc/1.0 (academic research)"


def norm(text: str) -> str:
    """Lower case, no accents, punctuation as spaces («¿...vid?» -> «vid»)."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in t).split())


class AgrovocClient:
    def __init__(self, pause_s: float = 0.5, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=40, headers={"User-Agent": UA})
        self.pause_s = pause_s

    def _get(self, path: str, params: dict) -> dict:
        time.sleep(self.pause_s)
        r = self.http.get(f"{API}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def find(self, term: str) -> str | None:
        """URI of the concept whose preferred or alternative label is exactly ``term`` (any of LANGS), else None."""
        target = norm(term)
        data = self._get("/search", {"query": term, "vocab": "agrovoc", "unique": "true"})
        for res in data.get("results", []):
            labels = [res.get("prefLabel"), res.get("altLabel"), res.get("matchedPrefLabel"), res.get("hiddenLabel")]
            if res.get("lang") in (None, *LANGS) and any(norm(x) == target for x in labels if x):
                return res["uri"]
        return None

    def concept(self, uri: str) -> dict:
        data = self._get("/agrovoc/data", {"uri": uri, "format": "application/ld+json"})
        node = next((n for n in data.get("graph", []) if n.get("uri") == uri), {})

        def labels(key: str) -> dict[str, list[str]]:
            vals = node.get(key) or []
            vals = vals if isinstance(vals, list) else [vals]
            out: dict[str, list[str]] = {}
            for v in vals:
                if isinstance(v, dict) and v.get("lang") in LANGS:
                    out.setdefault(v["lang"], []).append(v["value"])
            return out

        def uris(key: str) -> list[str]:
            vals = node.get(key) or []
            vals = vals if isinstance(vals, list) else [vals]
            return [v["uri"] for v in vals if isinstance(v, dict) and "uri" in v]

        return {"uri": uri, "pref": labels("prefLabel"), "alt": labels("altLabel"), "broader": uris("broader"),
                "exact_match": uris("exactMatch")}


def download(terms: list[dict], day: date | None = None, client: AgrovocClient | None = None) -> tuple[Snapshot, dict]:
    """``terms``: {"kind": crop|pest|ingredient, "key": graph key, "query": [labels to try in order]}."""
    client = client or AgrovocClient()
    snap = Snapshot("agrovoc", day or date.today(), root=DATA_ROOT, params={"terms": len(terms)})
    concepts: dict[str, dict] = {}
    links: list[dict] = []
    for t in terms:
        uri = None
        for q in t["query"]:
            if not q:
                continue
            try:
                uri = client.find(q)
            except httpx.HTTPError as e:
                links.append({**t, "uri": None, "error": f"{type(e).__name__}"})
                break
            if uri:
                break
        if uri and uri not in concepts:
            try:
                concepts[uri] = client.concept(uri)
            except httpx.HTTPError:
                uri = None
        links.append({"kind": t["kind"], "key": t["key"], "uri": uri, "query": t["query"]})
    snap.write_json("conceptos.json", concepts, "AGROVOC REST /agrovoc/data")
    snap.write_json("enlaces.json", links, "derivado: término del grafo -> concepto AGROVOC")
    snap.counts = {"terminos": len(terms), "con_concepto": sum(1 for x in links if x.get("uri")), "conceptos": len(concepts)}
    snap.close()
    return snap, snap.counts
