"""A phytosanitary program as the validator receives it: blocks of one crop, each with its planned harvest and the
markets its fruit goes to, and the applications made or planned on each block."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from domain.findings import Finding, Severity, worst


@dataclass(frozen=True)
class Block:
    key: str
    harvest_on: date
    markets: tuple[str, ...]


@dataclass(frozen=True)
class Application:
    block: str
    product_id: str
    applied_on: date
    pest: str | None = None   # SIGIA pest id, or "use:<class>" for other uses (e.g. growth regulators)


@dataclass(frozen=True)
class Program:
    crop: str
    blocks: tuple[Block, ...]
    applications: tuple[Application, ...]

    def block(self, key: str) -> Block | None:
        return next((b for b in self.blocks if b.key == key), None)


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> Severity | None:
        return worst(self.findings)

    def by_block(self) -> dict[str | None, list[Finding]]:
        out: dict[str | None, list[Finding]] = {}
        for f in self.findings:
            out.setdefault(f.block, []).append(f)
        return out

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]
