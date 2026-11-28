"""Count candidate documents in the DSpace repositories before downloading anything (corpus step 1).

Searches each DSpace source (INIA, SENASA, UNALM) with the crop and topic terms of the scope, through the public
discovery endpoint (``/discover/search/objects``), deduplicates by item uuid and applies the same filters as the
download: item type (``skip_types``), access (``skip_access``) and accepted licences. Writes a manifest of candidates
(no files) so the author can decide the size of the corpus before the download, and prints the counts per source, crop and
licence. Only metadata is requested; one request per page, with a pause, like the download client."""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from .sources import load_registry

CROPS = {
    "arandano": ["arándano", "arandano", "blueberry", "Vaccinium"],
    "palto": ["palto", "palta", "aguacate", "Persea americana"],
    "vid": ["vid", "uva de mesa", "Vitis vinifera"],
}
TOPICS = ["plagas", "enfermedades", "manejo integrado", "control biológico", "sanidad", "fitosanitario", "plaguicidas",
          "fertilización", "manejo agronómico", "residuos"]


@dataclass
class Candidate:
    source: str
    uuid: str
    handle: str
    title: str
    year: str
    type: str
    licence: str
    access: str
    crops: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    accepted: bool = True
    reason: str = ""


def _m(obj: dict, key: str) -> str:
    vals = obj.get("metadata", {}).get(key) or []
    return vals[0].get("value", "") if vals else ""


def _search(http: httpx.Client, api: str, query: str, page: int, size: int = 100) -> dict:
    r = http.get(f"{api}/discover/search/objects", params={"query": query, "dsoType": "ITEM", "size": size, "page": page})
    r.raise_for_status()
    return r.json()


def discover(out: Path, max_pages: int = 5, pause_s: float = 0.6) -> dict:
    cfg = load_registry()
    accepted = cfg.accepted_licences
    found: dict[str, Candidate] = {}
    with httpx.Client(timeout=60, headers={"User-Agent": "TP202620505-corpus/1.0 (academic research)"}) as http:
        for name, src in cfg.sources.items():
            if src.kind != "dspace" or not src.active:
                continue
            for crop, crop_terms in CROPS.items():
                for term in crop_terms:
                    for topic in TOPICS:
                        q = f'"{term}" AND "{topic}"'
                        for page in range(max_pages):
                            try:
                                data = _search(http, src.api, q, page)
                            except httpx.HTTPError as e:
                                print(f"[{name}] {q} p{page}: {e}")
                                break
                            res = data.get("_embedded", {}).get("searchResult", {})
                            objs = res.get("_embedded", {}).get("objects", [])
                            for o in objs:
                                it = o.get("_embedded", {}).get("indexableObject", {})
                                uid = it.get("uuid")
                                if not uid:
                                    continue
                                key = f"{name}:{uid}"
                                c = found.get(key)
                                if c is None:
                                    c = Candidate(source=name, uuid=uid, handle=it.get("handle", ""), title=it.get("name", ""),
                                                  year=_m(it, "dc.date.issued")[:4], type=_m(it, "dc.type"),
                                                  licence=_m(it, "dc.rights.uri") or _m(it, "dc.rights"),
                                                  access=_m(it, "dc.rights.accessRights") or _m(it, "datacite.rights"))
                                    found[key] = c
                                if crop not in c.crops:
                                    c.crops.append(crop)
                                if q not in c.queries:
                                    c.queries.append(q)
                            pages = res.get("page", {}).get("totalPages", 1)
                            time.sleep(pause_s)
                            if page + 1 >= pages:
                                break
            print(f"[{name}] {sum(1 for c in found.values() if c.source == name)} ítems distintos")
    for c in found.values():
        src = cfg.sources[c.source]
        t = c.type.lower()
        if any(s in t for s in src.skip_types):
            c.accepted, c.reason = False, f"tipo {c.type}"
        elif any(s.lower() in c.access.lower() for s in src.skip_access):
            c.accepted, c.reason = False, f"acceso {c.access}"
        elif c.licence and not any(a in c.licence for a in accepted):
            c.accepted, c.reason = False, f"licencia {c.licence}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for c in found.values():
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    ok = [c for c in found.values() if c.accepted]
    summary = {
        "candidatos": len(found), "aceptados": len(ok),
        "por_fuente": dict(Counter(c.source for c in ok)),
        "por_cultivo": dict(Counter(cr for c in ok for cr in c.crops)),
        "descartados_por": dict(Counter(c.reason.split(" ")[0] for c in found.values() if not c.accepted)),
        "por_tipo": dict(Counter(f"{c.source}:{c.type or '?'}" for c in ok).most_common(15)),
        "sin_licencia_declarada": sum(1 for c in ok if not c.licence),
    }
    return summary


# selection (corpus step 1) -------------------------------------------------------------------------------------------
CROP_IN_TITLE = r"ar[aá]ndano|blueberr|vaccinium|palt[ao]|aguacate|persea|\bvid\b|\buvas?\b|vitis|vi[ñn]edo"


def select(manifest: Path, out: Path) -> dict:
    """Curated list for the full corpus from the discovery manifest (decision of 11/11/2026):
    - UNALM: only items whose TITLE names one of the three crops (the rest only mention it in the abstract);
    - SENASA: every accepted item (few, and mostly general phytosanitary guides that apply to the three crops).
    Writes config/corpus_completo.yaml (source, uuid, why), which the download reads together with the seed list."""
    import re

    import yaml

    rx = re.compile(CROP_IN_TITLE, re.IGNORECASE)
    rows = [json.loads(line) for line in open(manifest, encoding="utf-8") if line.strip()]
    items, counts = [], Counter()
    for r in rows:
        if not r["accepted"]:
            continue
        if r["source"] == "unalm" and not rx.search(r["title"]):
            continue
        why = f"conteo {manifest.stem}: {', '.join(r['crops'])}; {'cultivo en el título' if r['source'] == 'unalm' else 'guía del SENASA'}"
        items.append({"source": r["source"], "uuid": r["uuid"], "why": why})
        counts[r["source"]] += 1
    out.write_text("# Generado por knowledge.corpus.discover.select; no editar a mano (rehacer con «corpus seleccionar»).\n"
                   + yaml.safe_dump({"items": items}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dict(counts)


# recovery: relevant theses whose title does not name the crop (corpus step 1, 11/11/2026) -----------------------------
RECOVER = """El repositorio asocia este trabajo con {crops}, aunque el título no nombre el cultivo. Decide con el mismo
criterio si entra al corpus. Ante la duda (un título fitosanitario general que probablemente incluye esos cultivos),
entra. Responde solo JSON: {{"entra": true|false, "motivo": "frase breve"}}"""


def recover(manifest: Path, generator, out: Path) -> dict:
    """Classifies the accepted UNALM candidates left out by the title rule (they only mention a crop in their
    metadata) against the corpus scope, and writes the ones in scope to config/corpus_recuperados.yaml, which the full
    download reads. Decisions are cached next to the manifest (recuperacion.json) so a re-run only asks the new ones."""
    import re

    import yaml

    from .curate import SCOPE, _json

    rx = re.compile(CROP_IN_TITLE, re.IGNORECASE)
    cache_path = manifest.with_name(manifest.stem + "_recuperacion.json")
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    rows = [json.loads(line) for line in open(manifest, encoding="utf-8") if line.strip()]
    pool = [r for r in rows if r["accepted"] and r["source"] == "unalm" and not rx.search(r["title"])]
    suffix = " /no_think" if getattr(generator, "name", "").startswith("local") else ""
    for r in pool:
        if r["uuid"] in cache:
            continue
        system = SCOPE + "\n\n" + RECOVER.format(crops=", ".join(r["crops"]))
        try:
            d = _json(generator.generate(system, f"Título: {r['title']}{suffix}").text)
        except Exception as e:
            d = {"entra": False, "motivo": f"sin decisión ({type(e).__name__})"}
        cache[r["uuid"]] = {"titulo": r["title"], "entra": bool(d.get("entra", False)), "motivo": d.get("motivo", "")}
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    items = [{"source": "unalm", "uuid": u, "why": f"recuperado: {v['motivo']}"} for u, v in cache.items() if v["entra"]]
    out.write_text("# Generado por knowledge.corpus.discover.recover; no editar a mano (rehacer con «corpus recuperar»).\n"
                   + yaml.safe_dump({"items": items}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"evaluados": len(cache), "recuperados": len(items)}
