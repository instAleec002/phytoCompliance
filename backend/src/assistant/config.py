"""Assistant configuration: ``config/assistant.yaml`` plus ``ASSISTANT_*`` environment overrides."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from shared.settings import REPO

DEFAULT_FILE = REPO / "backend" / "config" / "assistant.yaml"


class EmbedderConfig(BaseModel):
    name: str = "bge-m3"
    model: str = "BAAI/bge-m3"
    device: str = "auto"
    batch_size: int = 8
    max_length: int = 1024


class RetrievalConfig(BaseModel):
    signature: str = "latest"
    k_lexical: int = 30
    k_dense: int = 30
    rrf_k: int = 60
    top_k: int = 6
    min_dense_score: float = 0.45
    lexical_weight: float = 0.5
    dense_weight: float = 1.0
    lexical_ranking: str = "idf"   # ts_rank | idf (BM25-style weights; measured with S2)
    generic_weight: float = 1.0        # V4: factor on the fused score of generic sections (1.0 = off; measured in stage 3)
    lexical_header: str = "con"        # V3b: header in the lexical index: con | sin | peso (header at weight D)
    mmr_lambda: float | None = None    # MMR over the final candidates (None = off; 0.7 = mostly relevance)
    neighbors: int = 0                 # previous/next fragments of the same section added to what the generator reads
    expand_synonyms: bool = False      # AGROVOC + SIGIA synonyms in the lexical query (stage 4; measured in the ablation)
    max_per_document: int | None = None   # D1 (27/11/2026): cap of fragments per document among the candidates
    graph_list_weight: float | None = None  # D3 (27/11/2026): weight of the graph list in the fusion (None = off)
    entity_hop: bool = False           # D4 (27/11/2026): second hop by entity through the mentions index


class GeneratorConfig(BaseModel):
    name: str = "gemini"
    temperature: float = 0.1
    max_output_tokens: int = 4096
    seed: int | None = None            # fixed sampling seed for local models (None = Ollama draws one per call)


class ChatConfig(BaseModel):
    max_history_messages: int = 8     # earlier messages given to the rewrite and to the generator
    max_history_chars: int = 3000
    condense: bool = True             # rewrite follow-up questions as standalone queries before retrieval


class OrchestrationConfig(BaseModel):
    herramientas: bool = True         # stage 5: the agent with the exact core's tools and buscar_documentos (local generator)
    max_rondas: int = 4
    guarda_valores: bool = True       # output guard (27/11/2026): a value no tool returned goes back to the model once
    verificador: str | None = None    # sentence check of the final answer with this local model (None = off until measured)
    buscar_por_partes: bool = False   # D2 (27/11/2026): one document search per part of the question
    genericas: bool = False           # 27/11/2026: list and count tools (productos_para_plaga, ingredientes_sin_limite)


class AssistantConfig(BaseModel):
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generator: GeneratorConfig = Field(default_factory=GeneratorConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    generators: dict[str, dict[str, Any]] = Field(default_factory=dict)


def load_assistant_config(path: Path | None = None, env: bool = True) -> AssistantConfig:
    path = path or DEFAULT_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = AssistantConfig.model_validate(data or {})
    if env:
        if os.environ.get("ASSISTANT_EMBEDDER"):
            cfg.embedder.name = os.environ["ASSISTANT_EMBEDDER"]
        if os.environ.get("ASSISTANT_DEVICE"):
            cfg.embedder.device = os.environ["ASSISTANT_DEVICE"]
        if os.environ.get("ASSISTANT_GENERATOR"):
            cfg.generator.name = os.environ["ASSISTANT_GENERATOR"]
    return cfg
