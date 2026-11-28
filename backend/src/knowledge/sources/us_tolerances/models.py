"""Records of 40 CFR Part 180, as parsed from the eCFR."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class UsTolerance(_Record):
    commodity: str
    value_ppm: float | None          # ppm = mg/kg
    value_text: str
    expires_on: date | None          # time-limited tolerances (paragraph b) and scheduled revocations
    paragraph: str                   # "(a)", "(a)(1)", "(b)", "(c)", "(d)"
    kind: str                        # general, section_18, regional, indirect


class UsExemption(_Record):
    text: str                        # the exemption as written, with its conditions


class UsSection(BaseModel):
    number: str                      # "180.582"
    substance: str                   # "Pyraclostrobin"
    kind: str                        # tolerance or exemption
    heading: str
    tolerances: list[UsTolerance] = Field(default_factory=list)
    exemption: UsExemption | None = None
