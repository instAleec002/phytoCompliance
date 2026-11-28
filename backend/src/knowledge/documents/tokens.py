"""Token counters. Chunk budgets are expressed in tokens; the counter is swappable so the budget can later follow the
real tokenizer of the encoder (BGE-M3) without touching the chunkers."""
from __future__ import annotations

import math
from typing import Protocol

from .registry import TOKENIZERS, register


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


@register(TOKENIZERS, "approx")
class ApproxTokens:
    """About four characters per token, close to what XLM-RoBERTa-based tokenizers (BGE-M3) give for Spanish prose.
    Deterministic and dependency-free; good enough to size chunks, not to bill."""

    name = "approx"

    def __init__(self, chars_per_token: float = 4.0):
        self.chars_per_token = chars_per_token

    def count(self, text: str) -> int:
        return math.ceil(len(text) / self.chars_per_token) if text else 0
