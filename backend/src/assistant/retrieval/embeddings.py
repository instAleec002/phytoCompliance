"""Text encoders, by name. ``bge-m3`` is the thesis encoder (multilingual, dense vector from the normalized [CLS]
token, as its authors pool it); the LoRA-adapted version (HU0030) will be another entry that loads its adapter on top.
``device: auto`` uses CUDA when torch sees a GPU and the CPU otherwise, so moving to the training GPU is a
configuration change. ``hash`` is a deterministic encoder for tests: same text, same vector, no model."""
from __future__ import annotations

import hashlib
import math
from typing import Protocol

from knowledge.documents.registry import Registry, register

EMBEDDERS = Registry("codificador")
DIMENSION = 1024


class Embedder(Protocol):
    name: str
    dimension: int

    def encode(self, texts: list[str]) -> list[list[float]]: ...


@register(EMBEDDERS, "bge-m3")
class BgeM3:
    dimension = DIMENSION

    def __init__(self, model: str = "BAAI/bge-m3", device: str = "auto", batch_size: int = 8, max_length: int = 1024, **_):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        self.tokenizer = AutoTokenizer.from_pretrained(model)
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.model = AutoModel.from_pretrained(model, dtype=dtype).to(self.device).eval()
        self.batch_size, self.max_length = batch_size, max_length
        self.name = model.split("/")[-1].lower()

    def encode(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with self.torch.inference_mode():
            for i in range(0, len(texts), self.batch_size):
                batch = self.tokenizer(texts[i:i + self.batch_size], padding=True, truncation=True,
                                       max_length=self.max_length, return_tensors="pt").to(self.device)
                cls = self.model(**batch).last_hidden_state[:, 0]
                cls = self.torch.nn.functional.normalize(cls.float(), dim=-1)
                out += cls.cpu().tolist()
        return out


@register(EMBEDDERS, "hash")
class HashEmbedder:
    """Bag of hashed word trigrams, normalized: similar texts get similar vectors. For tests only."""

    dimension = DIMENSION
    name = "hash"

    def __init__(self, **_):
        pass

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for t in texts:
            v = [0.0] * DIMENSION
            words = t.lower().split()
            for w in words:
                for k in range(max(1, len(w) - 2)):
                    h = int(hashlib.md5(w[k:k + 3].encode()).hexdigest()[:8], 16)
                    v[h % DIMENSION] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors


def build_embedder(cfg) -> Embedder:
    return EMBEDDERS.create(cfg.name, model=cfg.model, device=cfg.device, batch_size=cfg.batch_size,
                            max_length=cfg.max_length)
