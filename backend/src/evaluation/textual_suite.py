"""Suite S2, textual questions over the corpus (protocol of Objetivo 2: at least 50, no less than 30 % multi-hop).

Sources, as approved by the author on 11/11/2026 (INIA is blocked): SENASA guides and manuals (level A) and UNALM theses and
professional reports (level C). Each question is tied to a document, a page and a literal answer span copied from that
page, so relevance does not depend on the chunking: a retrieved fragment counts as relevant when it contains the span
(or most of its words). Multi-hop questions join two pages of different documents that name the same pest or crop
(found with the controlled vocabulary) and need both to be answered.

Every item is checked before it is kept: the span must appear literally on its page (accents and spacing ignored), the
question must not copy the span, and a multi-hop item needs one span per page. Pages come straight from the PDF with
PyMuPDF, not from the pipeline, so the suite stays independent of the extractor and the chunker too. The source
documents are listed so they can be left out of any training data."""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from knowledge.vocabulary.agrovoc import norm

SINGLE = """Eres un evaluador. Recibes una página de un documento técnico agrícola peruano. Escribe UNA pregunta que un
técnico de sanidad vegetal haría y que esta página responde de forma específica. No copies frases de la página en la
pregunta. La pregunta debe entenderse sola, sin ver la página: nombra el producto, la plaga, el cultivo o el tema
concreto; nunca escribas «el documento», «el producto», «la página» ni «según el texto». Copia, literalmente, el
fragmento de la página (de 8 a 40 palabras) que contiene la respuesta.
Responde solo JSON: {"pregunta": "...", "respuesta": "una o dos oraciones", "fragmento": "texto copiado tal cual"}"""

MULTI = """Eres un evaluador. Recibes dos páginas de documentos técnicos agrícolas distintos que tratan el mismo tema
({tema}). Escribe UNA pregunta que solo se puede responder combinando información de ambas páginas (por ejemplo, el
síntoma o el daño de una plaga que describe una y su control que describe la otra). No copies frases en la pregunta.
La pregunta debe nombrar «{tema}» y tratar sobre eso en ambas páginas; nunca escribas «el documento», «la página» ni «el texto».
Copia, literalmente, un fragmento de cada página (8 a 40 palabras) que sostenga la respuesta.
Responde solo JSON: {{"pregunta": "...", "respuesta": "...", "fragmento_1": "copiado de la página 1", "fragmento_2": "copiado de la página 2"}}"""


VAGUE = re.compile(r"(?i)\b(el|este|dicho) (documento|texto|informe|manual|producto)\b|\bla página\b|según el texto"
                   # tied to one study: no user asks about «the trial» or «treatment T3» of a thesis they have not read
                   r"|\b(el|este|dicho|del|en el|la|esta) (ensayo|experimento|estudio|tratamiento|fundo|turno|trabajo|"
                   r"proyecto|tesis|autor|investigación|empresa|evaluación)\b|\bT\d\b|\btratamiento \w*\d|\bobtenid[oa]s?\b"
                   r"|\bse (obtuvo|encontró|registró|observó)\b")

QUALITY = """Eres revisor de un conjunto de evaluación. Un técnico de sanidad vegetal o un exportador agrícola peruano
consulta un asistente. Decide si la pregunta sirve: debe entenderse sola (sin ver ningún documento), tener una respuesta
precisa y ser algo que ese usuario preguntaría (manejo de plagas, productos, normas, cultivos, procedimientos), no un
dato propio de un estudio, ensayo, empresa o fundo concreto.
Responde solo JSON: {"sirve": true|false, "motivo": "breve"}"""


def good_question(generator, question: str) -> bool:
    if VAGUE.search(question):
        return False
    return _json(generator.generate(QUALITY, f"Pregunta: {question}").text).get("sirve") is True


@dataclass
class TextualItem:
    qid: str
    tipo: str                           # un_salto | varios_saltos
    pregunta: str
    respuesta: str
    evidencias: list[dict] = field(default_factory=list)     # doc_id, pagina, fragmento
    tema: str = ""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def pages_of(path: Path, min_words: int = 120) -> list[tuple[int, str]]:
    import fitz

    out = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            t = " ".join(page.get_text("text").split())
            if len(t.split()) >= min_words and not re.search(r"(?i)referencias|bibliograf|índice|indice general|agradecimient", t[:200]):
                out.append((i, t))
    return out


def span_ok(span: str, page: str, question: str) -> bool:
    s, p = norm(span), norm(page)
    words = s.split()
    if not (8 <= len(words) <= 45) or s not in p:
        return False
    q = set(norm(question).split())
    return len(set(words) & q) / max(1, len(set(words))) < 0.6        # the question must not copy the span


def build(records: list[dict], folder: Path, generator, vocabulary, n_single: int = 40, n_multi: int = 20,
          seed: int = 20261111) -> tuple[list[TextualItem], list[str]]:
    rng = random.Random(seed)
    docs = [r for r in records if r["status"] == "descargado" and r["source"] in ("senasa", "unalm")
            and r["file"] and r["file"].lower().endswith(".pdf")]
    rng.shuffle(docs)
    pages: dict[str, list[tuple[int, str]]] = {}

    def doc_pages(r) -> list[tuple[int, str]]:
        if r["doc_id"] not in pages:
            try:
                pages[r["doc_id"]] = pages_of(folder / r["file"])
            except Exception:  # noqa: BLE001 - an unreadable PDF just gives no pages
                pages[r["doc_id"]] = []
        return pages[r["doc_id"]]

    items: list[TextualItem] = []
    used: set[str] = set()
    # single hop: alternate SENASA and UNALM, one page per document
    by_src = {s: [r for r in docs if r["source"] == s] for s in ("senasa", "unalm")}
    turn = 0
    while sum(i.tipo == "un_salto" for i in items) < n_single and any(by_src.values()):
        src = ("senasa", "unalm")[turn % 2]
        turn += 1
        if not by_src[src]:
            continue
        r = by_src[src].pop()
        ps = doc_pages(r)
        if not ps:
            continue
        pg, text = rng.choice(ps)
        d = _json(generator.generate(SINGLE, f"Página {pg} de «{r['title']}»:\n{text[:6000]}").text)
        if d.get("pregunta") and span_ok(d.get("fragmento", ""), text, d["pregunta"]) and good_question(generator, d["pregunta"]):
            items.append(TextualItem(f"t{len(items) + 1:03d}", "un_salto", d["pregunta"].strip(), d.get("respuesta", "").strip(),
                                     [{"doc_id": r["doc_id"], "pagina": pg, "fragmento": d["fragmento"].strip()}]))
            used.add(r["doc_id"])
    # multi hop: two documents that share a pest (or crop) named in a page of each
    pool = [r for r in docs if r["doc_id"] not in used]
    tries = 0
    stats = Counter()
    # index first: which pests each document names, and on which pages (a random pair almost never shares one)
    by_pest: dict[str, list[tuple[dict, int, str]]] = {}
    terms: dict[str, object] = {}
    for r in pool:
        seen = set()
        for pg, tx in doc_pages(r):
            for t in vocabulary.find(tx):
                if t.kind == "pest" and t.key not in seen:
                    seen.add(t.key)
                    terms[t.key] = t
                    by_pest.setdefault(t.key, []).append((r, pg, tx))
    shared = sorted(k for k, v in by_pest.items() if len(v) > 1)
    print(f"plagas nombradas en dos o más documentos: {len(shared)}")
    while sum(i.tipo == "varios_saltos" for i in items) < n_multi and tries < n_multi * 10 and shared:
        tries += 1
        key = rng.choice(shared)
        cands = [c for c in by_pest[key] if c[0]["doc_id"] not in used]
        mixed = [(x, y) for x in cands for y in cands if x[0]["source"] == "senasa" and y[0]["source"] == "unalm"]
        if mixed:
            (a, pg_a, tx_a), (b, pg_b, tx_b) = rng.choice(mixed)       # prefer an official page with a thesis page
        elif len(cands) > 1:
            (a, pg_a, tx_a), (b, pg_b, tx_b) = rng.sample(cands, 2)
        else:
            shared.remove(key)
            stats["sin_par_libre"] += 1
            continue
        topic = sorted(terms[key].labels, key=len)[-1]
        d = _json(generator.generate(MULTI.format(tema=topic), f"Página 1 («{a['title']}», p. {pg_a}):\n{tx_a[:3500]}\n\n"
                                                              f"Página 2 («{b['title']}», p. {pg_b}):\n{tx_b[:3500]}").text)
        names_topic = any(norm(lb) in norm(d.get("pregunta", "")) for lb in terms[key].labels)
        ok = d.get("pregunta") and names_topic and \
            span_ok(d.get("fragmento_1", ""), tx_a, d["pregunta"]) and span_ok(d.get("fragmento_2", ""), tx_b, d["pregunta"]) and \
            good_question(generator, d["pregunta"])
        stats["aceptadas" if ok else "rechazadas_por_el_control"] += 1
        if ok:
            items.append(TextualItem(f"t{len(items) + 1:03d}", "varios_saltos", d["pregunta"].strip(), d.get("respuesta", "").strip(),
                                     [{"doc_id": a["doc_id"], "pagina": pg_a, "fragmento": d["fragmento_1"].strip()},
                                      {"doc_id": b["doc_id"], "pagina": pg_b, "fragmento": d["fragmento_2"].strip()}], topic))
            used |= {a["doc_id"], b["doc_id"]}
            pool = [r for r in pool if r["doc_id"] not in used]
    print(f"varios saltos: {tries} intentos, {dict(stats)}")
    return items, sorted(used)


def relevant(fragment_text: str, evidence: dict, threshold: float = 0.7) -> bool:
    """A retrieved fragment is relevant to an evidence span when it contains the span, or at least ``threshold`` of its
    words in order-insensitive form (a fragment boundary may cut the span). Independent of how the corpus was chunked."""
    span = norm(evidence["fragmento"])
    text = norm(fragment_text)
    if span in text:
        return True
    words = [w for w in span.split() if len(w) > 3]          # content words only: «de», «la», «los» are everywhere
    tset = set(text.split())
    return len(words) >= 5 and sum(1 for w in words if w in tset) / len(words) >= threshold


def as_rows(items: list[TextualItem]) -> list[dict]:
    return [asdict(i) for i in items]
