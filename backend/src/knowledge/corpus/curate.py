"""Topical curation of a corpus snapshot (corpus step 1, 11/11/2026).

The DSpace search matches any item that mentions a crop, and a title regex cannot tell crop management from a market
study («Pisco» is also a city). Each downloaded academic item is classified against an explicit scope with the cloud
generator, from its title, and the decision is written back to the snapshot's documents.json (status «excluido» with
reason «fuera de alcance: ...»), so the counter, the index and the thesis see the same curated corpus. Official (A) and
internal documents are not curated: they were selected by hand or written for the case.

The decisions are also saved as curacion.json in the snapshot, so they can be reviewed and the scope revised."""
from __future__ import annotations

import json
import re
from pathlib import Path

SCOPE = """Decides si un documento entra al corpus de un asistente de sanidad vegetal y cumplimiento fitosanitario para
agroexportadoras peruanas de arándano, palto y uva de mesa.

ENTRA si trata, para alguno de esos tres cultivos (o para varios cultivos incluyéndolos):
- plagas, enfermedades, nematodos, malezas, su monitoreo, umbrales o manejo integrado;
- plaguicidas, residuos, límites, carencias, resistencia, control biológico o etológico;
- certificación fitosanitaria, requisitos de exportación, inocuidad en campo;
- manejo agronómico del cultivo (fertilización, riego, poda, fenología, suelo) porque condiciona las decisiones sanitarias.

NO ENTRA si trata sobre todo de: mercados, comercialización, economía, finanzas, planes de negocio; procesamiento
agroindustrial, química de alimentos, antioxidantes, poscosecha de laboratorio; vino o pisco (salvo manejo sanitario
del viñedo); ganadería o alimentación animal; genética, mejoramiento o caracterización molecular; otros cultivos sin
incluir a los tres.

Responde solo JSON: {"entra": true|false, "motivo": "frase breve"}"""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


def curate(folder: Path, generator, sources: tuple[str, ...] = ("unalm",)) -> dict:
    path = folder / "documents.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    out = folder / "curacion.json"
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for r in records:
        prev = done.get(r["doc_id"])
        if r["source"] not in sources or r["status"] != "descargado" or (prev and not prev["motivo"].startswith("sin decisión")):
            continue
        if (r.get("why") or "").startswith("recuperado"):   # already classified by discover.recover
            done[r["doc_id"]] = {"titulo": r["title"], "entra": True, "motivo": r["why"]}
            continue
        try:
            # Qwen3 thinks before answering unless told not to; a yes/no classification does not need it
            suffix = " /no_think" if generator.name.startswith("local") else ""
            d = _json(generator.generate(SCOPE, f"Título: {r['title']}{suffix}").text)
        except Exception as e:   # one failed call keeps the document (it can be curated again later)
            d = {"entra": True, "motivo": f"sin decisión ({type(e).__name__}); se conserva"}
        done[r["doc_id"]] = {"titulo": r["title"], "entra": bool(d.get("entra", True)), "motivo": d.get("motivo", "")}
        out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    # manual decisions win (config/corpus_curacion_manual.yaml, matched by the start of the title)
    import yaml

    from .sources import CONFIG
    manual = yaml.safe_load((CONFIG / "corpus_curacion_manual.yaml").read_text(encoding="utf-8")) if (CONFIG / "corpus_curacion_manual.yaml").exists() else {}
    for m in (manual or {}).get("entran", []):
        for d in done.values():
            if d["titulo"].lower().startswith(m["titulo"].lower()[:60]):
                d.update(entra=True, motivo=f"decisión manual: {m['motivo']}")
    out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in records:
        d = done.get(r["doc_id"])
        if d and d["entra"] and r["status"] == "excluido" and r["reason"].startswith("fuera de alcance"):
            r["status"], r["reason"] = "descargado", ""
        if d and not d["entra"] and r["status"] == "descargado":
            r["status"], r["reason"] = "excluido", f"fuera de alcance: {d['motivo']}"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    kept = sum(1 for d in done.values() if d["entra"])
    return {"curados": len(done), "entran": kept, "fuera_de_alcance": len(done) - kept}
