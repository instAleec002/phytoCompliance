"""The data sources an API request works with. In production they come from the graph (one connection per request);
the tests replace them with in-memory ones through ``app.dependency_overrides``."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends

from domain.ports import LimitSource, ModeOfActionSource, RegistrySource, ToxicologySource


class CatalogSource(Protocol):
    def crops(self) -> list[dict]: ...

    def markets(self) -> list[dict]: ...

    def pests(self, crop: str) -> list[dict]: ...

    def products(self, crop: str, pest: str) -> list[dict]: ...

    def ingredients(self, crop: str | None = None, query: str | None = None, limit: int = 50) -> list[dict]: ...


@dataclass
class Sources:
    limits: LimitSource
    registry: RegistrySource
    moa: ModeOfActionSource
    toxicology: ToxicologySource
    catalog: CatalogSource


def graph_sources() -> Iterator[Sources]:
    from knowledge.graph.age import AgeGraph
    from knowledge.graph.catalog import GraphCatalog
    from knowledge.graph.repository import GraphModeOfAction, GraphRepository, GraphToxicology

    graph = AgeGraph.connect()
    try:
        repo = GraphRepository(graph)
        yield Sources(limits=repo, registry=repo, moa=GraphModeOfAction(graph), toxicology=GraphToxicology(graph),
                      catalog=GraphCatalog(graph))
    finally:
        graph.close()


# the type routers declare: Annotated keeps the dependency out of the argument defaults
SourcesDep = Annotated[Sources, Depends(graph_sources)]
