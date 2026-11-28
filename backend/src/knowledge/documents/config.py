"""Pipeline configuration: ``config/documents.yaml``, then ``DOCS_*`` environment variables, then explicit overrides
(CLI flags or a benchmark loop). Names are checked against the registries, so a typo fails at start-up with the list
of what exists instead of halfway through a corpus.

Environment variables: ``DOCS_ROUTE``, ``DOCS_EXTRACTOR_PDF``, ``DOCS_EXTRACTOR_DOCX``, ``DOCS_EXTRACTOR_XLSX``,
``DOCS_STEPS`` (comma list), ``DOCS_CHUNKER``, ``DOCS_MAX_TOKENS``, ``DOCS_CONTEXTUAL_HEADER`` (on/off),
``DOCS_TOKENS``."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from shared.settings import REPO

from . import chunkers, extractors, steps  # noqa: F401  (fill the registries)
from . import tokens as _tokens  # noqa: F401
from .registry import CHUNKERS, EXTRACTORS, STEPS, TOKENIZERS
from .routes import ROUTES

DEFAULT_FILE = REPO / "backend" / "config" / "documents.yaml"


class ChunkerConfig(BaseModel):
    name: str = "structural"
    max_tokens: int = 480
    min_tokens: int = 80
    overlap_tokens: int = 60
    child_tokens: int = 160
    # Stage 3 variants (11/11/2026). None = off, and then they stay out of the signature, so a configuration
    # without them keeps the signature it always had (its chunks, vectors and judgments stay valid).
    merge_section_tokens: int | None = None    # V2: a section under this many tokens joins the next one of the same parent
    generic_sections: str | None = None        # V4: "drop" leaves out abstract, introduction, conclusions, objectives…
    table_rows: bool | None = None             # V6: a table over the budget is split by rows, repeating the header row
    table_text: str | None = None              # V6b: "filas" = the encoder reads tables as one sentence per row

    def params(self) -> dict[str, Any]:
        return self.model_dump(exclude={"name"}, exclude_none=True)


class PipelineConfig(BaseModel):
    route: str = "markdown"
    extractors: dict[str, str] = Field(default_factory=lambda: {"pdf": "opendataloader", "docx": "docx", "xlsx": "xlsx"})
    extractor_options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=lambda: ["text", "furniture", "tables", "outline", "sections"])
    step_options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    contextual_header: bool = True
    header: str | None = None                  # V3: "short" = title and the last two section levels
    tokens: str = "approx"
    language: str = "es"

    @field_validator("route")
    @classmethod
    def _route(cls, v: str) -> str:
        if v not in ROUTES:
            raise ValueError(f"ruta desconocida {v!r}; disponibles: {', '.join(ROUTES)}")
        return v

    @field_validator("extractors")
    @classmethod
    def _extractors(cls, v: dict[str, str]) -> dict[str, str]:
        for fmt, name in v.items():
            if name not in EXTRACTORS:
                raise ValueError(f"extractor desconocido {name!r} para .{fmt}; disponibles: {', '.join(sorted(EXTRACTORS))}")
            if fmt not in EXTRACTORS[name].formats:
                raise ValueError(f"el extractor {name!r} no lee .{fmt}")
        return v

    @field_validator("steps")
    @classmethod
    def _steps(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in STEPS]
        if unknown:
            raise ValueError(f"pasos desconocidos {unknown}; disponibles: {', '.join(sorted(STEPS))}")
        return v

    @field_validator("chunker")
    @classmethod
    def _chunker(cls, v: ChunkerConfig) -> ChunkerConfig:
        if v.name not in CHUNKERS:
            raise ValueError(f"troceador desconocido {v.name!r}; disponibles: {', '.join(sorted(CHUNKERS))}")
        return v

    @field_validator("tokens")
    @classmethod
    def _tokens(cls, v: str) -> str:
        if v not in TOKENIZERS:
            raise ValueError(f"contador de tokens desconocido {v!r}; disponibles: {', '.join(sorted(TOKENIZERS))}")
        return v

    def signature(self) -> str:
        """Short hash of everything that changes the output: stored with every chunk, so two runs with different
        settings can never be mixed up in the index or in a benchmark table."""
        # exclude_none: options added later that are off (None) do not change the signature of earlier configurations
        return hashlib.sha256(json.dumps(self.model_dump(exclude_none=True), sort_keys=True).encode()).hexdigest()[:12]

    def with_overrides(self, **changes) -> PipelineConfig:
        data = self.model_dump()
        for key, value in changes.items():
            if value is None:
                continue
            if key in ("pdf", "docx", "xlsx"):
                data["extractors"][key] = value
            elif key in ("max_tokens", "min_tokens", "overlap_tokens", "child_tokens", "merge_section_tokens"):
                data["chunker"][key] = int(value)
            elif key in ("generic_sections", "table_rows", "table_text"):
                data["chunker"][key] = value
            elif key == "chunker" and isinstance(value, str):
                data["chunker"]["name"] = value
            else:
                data[key] = value
        return PipelineConfig.model_validate(data)


def _env_overrides() -> dict[str, Any]:
    e = os.environ
    out: dict[str, Any] = {
        "route": e.get("DOCS_ROUTE"),
        "pdf": e.get("DOCS_EXTRACTOR_PDF"),
        "docx": e.get("DOCS_EXTRACTOR_DOCX"),
        "xlsx": e.get("DOCS_EXTRACTOR_XLSX"),
        "chunker": e.get("DOCS_CHUNKER"),
        "max_tokens": e.get("DOCS_MAX_TOKENS"),
        "tokens": e.get("DOCS_TOKENS"),
    }
    if e.get("DOCS_STEPS"):
        out["steps"] = [s.strip() for s in e["DOCS_STEPS"].split(",") if s.strip()]
    if e.get("DOCS_CONTEXTUAL_HEADER"):
        out["contextual_header"] = e["DOCS_CONTEXTUAL_HEADER"].strip().lower() in ("on", "1", "true", "yes", "sí", "si")
    return out


def load_config(path: Path | None = None, env: bool = True, **overrides) -> PipelineConfig:
    path = path or DEFAULT_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = PipelineConfig.model_validate(data or {})
    if env:
        cfg = cfg.with_overrides(**_env_overrides())
    return cfg.with_overrides(**overrides)
