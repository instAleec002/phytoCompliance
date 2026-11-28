"""Shapes shared by several endpoints."""
from __future__ import annotations

from dataclasses import asdict
from enum import Enum

from pydantic import BaseModel, Field

from domain.findings import Finding, worst


class FindingOut(BaseModel):
    code: str = Field(description="Código estable del hallazgo, p. ej. PHI_NOT_MET o MRL_EXCEEDED")
    severity: str = Field(description="blocking, risk o info")
    message: str
    block: str | None = None
    product_id: str | None = None
    ingredient: str | None = None
    market: str | None = None
    evidence: dict = Field(default_factory=dict, description="Datos en que se apoya: norma, instantánea, cifras")

    @classmethod
    def of(cls, f: Finding) -> FindingOut:
        return cls(**{k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(f).items()})


def verdict(findings: list[Finding]) -> str | None:
    level = worst(findings)
    return level.value if level else None
