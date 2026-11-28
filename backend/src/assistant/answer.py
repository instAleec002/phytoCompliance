"""A cited answer to a question (HU0012): retrieve, decide whether there is evidence, generate, and keep only the
citations the text actually uses. The trace records the mode, the model, the signature searched, the passages with
their ranks and the times, so every answer can be audited and the evaluation can read the same object."""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

from knowledge.corpus.store import CorpusStore

from .config import AssistantConfig, load_assistant_config
from .generation.generators import build_generator
from .generation.prompt import CONDENSE, NO_EVIDENCE, SYSTEM, build_prompt, condense_prompt
from .retrieval.embeddings import build_embedder
from .retrieval.search import HybridRetriever, Passage, latest_signature

CITE = re.compile(r"\[(\d{1,2})\]")


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    title: str
    source: str
    level: str
    url: str
    section: list[str]
    pages: list[int]
    text: str


@dataclass
class AnswerResult:
    question: str
    text: str
    evidence: bool
    citations: list[Citation] = field(default_factory=list)
    trace: dict = field(default_factory=dict)
    graph_rows: list[dict] = field(default_factory=list)      # stage 5: exact-core rows the answer cites as [G1]…


class Answerer:
    def __init__(self, retriever: HybridRetriever, generator, top_k: int, max_history_messages: int = 8,
                 max_history_chars: int = 3000, condense: bool = True, agente=None):
        """``agente`` (stage 5): with it, the answer comes from the model with the exact core's tools and
        buscar_documentos (this retriever); without it, from the passages alone as before."""
        self.retriever, self.generator, self.top_k = retriever, generator, top_k
        self.agente = agente
        self.max_history_messages, self.max_history_chars, self.condense = max_history_messages, max_history_chars, condense

    def standalone(self, question: str, history: list[tuple[str, str]]) -> tuple[str, float]:
        """The question rewritten with the conversation so retrieval can search it alone. Without history, or with a
        generator that cannot rewrite (extractive), the question is used as it is."""
        if not history or not self.condense or self.generator.name == "extractive":
            return question, 0.0
        gen = self.generator.generate(CONDENSE, condense_prompt(question, history, self.max_history_chars))
        query = gen.text.strip().splitlines()[0].strip(' "«»') if gen.text.strip() else ""
        return (query or question), gen.seconds

    def answer(self, question: str, history: list[tuple[str, str]] | None = None) -> AnswerResult:
        """``history``: earlier messages of the conversation as (rol, texto), oldest first, rol «usuario» or
        «asistente»; only the last ``max_history_messages`` are used."""
        history = (history or [])[-self.max_history_messages:]
        query, condense_s = self.standalone(question, history)
        if self.agente is not None:
            return self._con_herramientas(question, query, condense_s, history)
        t0 = time.perf_counter()
        passages = self.retriever.retrieve(query)
        t1 = time.perf_counter()
        trace = {"signature": self.retriever.signature, "embedder": self.retriever.embedder.name,
                 "generator": self.generator.name, "standalone_query": query, "history_messages": len(history),
                 "condense_s": condense_s, "retrieval_s": round(t1 - t0, 2),
                 "passages": [{k: v for k, v in asdict(p).items() if k not in ("text", "context", "header")}
                              for p in passages]}
        if not passages:
            return AnswerResult(question, NO_EVIDENCE, False, trace={**trace, "reason": "sin pasajes recuperados"})
        gen = self.generator.generate(SYSTEM, build_prompt(question, passages, history, self.max_history_chars))
        trace.update({"generation_s": gen.seconds, "model": gen.model, "usage": gen.usage})
        if NO_EVIDENCE in gen.text:
            return AnswerResult(question, NO_EVIDENCE, False, trace={**trace, "reason": "el generador no halló respaldo"})
        used = sorted({int(n) for n in CITE.findall(gen.text) if 1 <= int(n) <= len(passages)})
        citations = [_citation(n, passages[n - 1]) for n in used]
        trace["uncited_answer"] = not used
        return AnswerResult(question, gen.text, True, citations, trace)


    def _con_herramientas(self, question, query, condense_s, history) -> AnswerResult:
        r = self.agente.responder(query)
        usados = r.citas.citas_documentos                       # RespuestaAgente: solo citas a lo que se consultó
        filas = [f for f in r.filas if f["id"] in r.citas.citas_grafo]
        trace = {"signature": self.retriever.signature, "embedder": self.retriever.embedder.name,
                 "generator": f"agente:{self.agente.model}", "standalone_query": query, "history_messages": len(history),
                 "condense_s": condense_s, "generation_s": r.segundos, "rondas": r.rondas, "tokens": r.tokens,
                 "llamadas": [{"nombre": c["nombre"], "argumentos": c["argumentos"]} for c in r.llamadas],
                 "filas_grafo": filas, "corregido": r.corregido, "retiradas": r.retiradas,
                 "texto_sin_verificar": r.texto_sin_verificar, "evidencia_sin_verificar": r.evidencia_sin_verificar}
        if not usados and not filas:
            # sin pasajes ni filas citados no hay respaldo: no se muestra una respuesta sin evidencia
            return AnswerResult(question, NO_EVIDENCE, False, trace={**trace, "reason": "la respuesta no cita evidencia",
                                                                     "texto_descartado": r.texto})
        return AnswerResult(question, r.texto, True, [_citation(n, r.pasajes[n - 1]) for n in usados], trace, filas)


def _citation(n: int, p: Passage) -> Citation:
    return Citation(n=n, chunk_id=p.chunk_id, doc_id=p.doc_id, title=p.title, source=p.source, level=p.level,
                    url=p.url, section=p.section, pages=p.pages, text=p.text)


def build_answerer(store: CorpusStore, config: AssistantConfig | None = None, generator: str | None = None,
                   embedder=None) -> Answerer:
    cfg = config or load_assistant_config()
    embedder = embedder or build_embedder(cfg.embedder)
    sig = cfg.retrieval.signature
    if sig == "latest":
        sig = latest_signature(store.conn, embedder.name)
        if sig is None:
            raise RuntimeError(f"No hay un índice con el codificador {embedder.name}: corre «corpus indexar».")
    r = cfg.retrieval
    vocabulary = graph_vocabulary = None
    if r.expand_synonyms or r.graph_list_weight or r.entity_hop:
        from interfaces.jobs.vocabulary import load_vocabulary
        loaded = load_vocabulary()
        vocabulary = loaded if r.expand_synonyms else None
        graph_vocabulary = loaded if (r.graph_list_weight or r.entity_hop) else None
    retriever = HybridRetriever(store.conn, embedder, sig, r.k_lexical, r.k_dense, r.rrf_k, r.top_k, r.min_dense_score,
                                r.lexical_weight, r.dense_weight, vocabulary, r.lexical_ranking, r.generic_weight,
                                r.lexical_header, r.mmr_lambda, r.neighbors, r.max_per_document,
                                r.graph_list_weight, graph_vocabulary, entity_hop=r.entity_hop)
    agente = None
    if cfg.orchestration.herramientas and (generator or cfg.generator.name) == "local":
        from interfaces.jobs.vocabulary import load_vocabulary
        from knowledge.normalization.ingredients import Aliases, spanish_names

        from .orchestration.agente import Agente
        from .orchestration.tools import GrafoPorConsulta, Herramientas

        local = cfg.generators.get("local", {})
        aliases = Aliases.load()
        verificador = None
        if cfg.orchestration.verificador:
            from .orchestration.verificacion import Juez
            verificador = Juez(local.get("base_url", "http://localhost:11434/v1"), cfg.orchestration.verificador)
        agente = Agente(local.get("base_url", "http://localhost:11434/v1"), local.get("model", "qwen3:8b"),
                        Herramientas(GrafoPorConsulta(), aliases, spanish_names(aliases), load_vocabulary()),
                        temperature=cfg.generator.temperature, max_rondas=cfg.orchestration.max_rondas,
                        documentos=retriever.retrieve, pasajes_por_busqueda=r.top_k,
                        guarda_valores=cfg.orchestration.guarda_valores, verificador=verificador,
                        por_partes=cfg.orchestration.buscar_por_partes, seed=cfg.generator.seed,
                        genericas=cfg.orchestration.genericas)
    return Answerer(retriever, build_generator(cfg.generator, cfg.generators, generator), r.top_k,
                    cfg.chat.max_history_messages, cfg.chat.max_history_chars, cfg.chat.condense, agente)
