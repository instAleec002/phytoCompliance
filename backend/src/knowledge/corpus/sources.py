"""The source registry (``config/corpus_sources.yaml``) and the seed list (``config/corpus_seed.yaml``)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from shared.settings import REPO

CONFIG = REPO / "backend" / "config"


class Source(BaseModel):
    key: str = ""
    name: str
    level: Literal["A", "B", "C", "interno"]
    kind: Literal["dspace", "local"]
    # a source that refuses our requests is paused here instead of retried: nothing contacts it, and only documents
    # downloaded before the pause are kept (policy of 11/11/2026)
    active: bool = True
    paused_reason: str = ""
    api: str | None = None
    handle_url: str | None = None
    build_links: bool = False
    skip_types: list[str] = Field(default_factory=list)
    skip_access: list[str] = Field(default_factory=list)
    skip_files: list[str] = Field(default_factory=list)
    folder: str | None = None
    licence: str | None = None
    rules: dict = Field(default_factory=dict)

    def skips_file(self, name: str) -> bool:
        return any(re.search(p, name, re.IGNORECASE) for p in self.skip_files)


class SeedItem(BaseModel):
    source: str
    uuid: str | None = None
    file: str | None = None
    why: str = ""


class Registry(BaseModel):
    sources: dict[str, Source]
    accepted_licences: list[str]

    def licence_ok(self, licence: str | None) -> bool:
        return bool(licence) and any(a in licence for a in self.accepted_licences)


def load_registry(path: Path | None = None) -> Registry:
    data = yaml.safe_load((path or CONFIG / "corpus_sources.yaml").read_text(encoding="utf-8"))
    for key, src in data["sources"].items():
        src["key"] = key
    return Registry.model_validate(data)


def load_seed(path: Path | None = None) -> list[SeedItem]:
    data = yaml.safe_load((path or CONFIG / "corpus_seed.yaml").read_text(encoding="utf-8"))
    return [SeedItem.model_validate(x) for x in data["items"]]
