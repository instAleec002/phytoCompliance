"""Named registries: every swappable piece of the pipeline is registered under a name, and the configuration chooses
by name. Adding an implementation is one decorated class; nothing else changes."""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class Registry(dict[str, Callable[..., object]]):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def create(self, name: str, **params):
        if name not in self:
            raise KeyError(f"{self.kind} desconocido: {name!r}. Disponibles: {', '.join(sorted(self))}")
        return self[name](**params)


EXTRACTORS = Registry("extractor")
STEPS = Registry("paso")
CHUNKERS = Registry("troceador")
TOKENIZERS = Registry("contador de tokens")


def register(registry: Registry, name: str) -> Callable[[T], T]:
    def deco(factory: T) -> T:
        if name in registry:
            raise ValueError(f"{registry.kind} {name!r} ya está registrado")
        registry[name] = factory  # type: ignore[assignment]
        return factory

    return deco
