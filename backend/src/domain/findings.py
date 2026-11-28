"""A finding is what every rule returns: a code the API and the evaluation can count, a severity, a message in Spanish
for the user, and the evidence it rests on (regulation, snapshot, figures), so nothing has to be produced later."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    BLOCKING = "blocking"   # breaks a rule: the program or lot cannot go as it is
    RISK = "risk"           # may break a rule, depending on the residue at harvest or on missing data
    INFO = "info"           # worth knowing, no rule is broken


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    block: str | None = None
    product_id: str | None = None
    ingredient: str | None = None
    market: str | None = None
    evidence: dict = field(default_factory=dict)


def worst(findings: list[Finding]) -> Severity | None:
    for level in (Severity.BLOCKING, Severity.RISK, Severity.INFO):
        if any(f.severity is level for f in findings):
            return level
    return None
