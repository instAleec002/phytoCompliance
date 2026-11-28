"""Limit in force for an ingredient, crop and market on a day, its versions, and the ones still to apply."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from domain.compliance.limits import limit_on, upcoming

from ..schemas.limits import LimitOut, VersionOut
from ..sources import SourcesDep

router = APIRouter(prefix="/lmr", tags=["límites"])


@router.get("", response_model=LimitOut, summary="Límite vigente en una fecha (hoy si no se indica)")
def limit(sources: SourcesDep, ingrediente: str = Query(examples=["pyraclostrobin"]),
          cultivo: str = Query(examples=["blueberry"]), mercado: str = Query(examples=["EU"]),
          fecha: date | None = None):
    return LimitOut.of(limit_on(sources.limits, ingrediente, cultivo, mercado, fecha or date.today()))


@router.get("/versiones", response_model=list[VersionOut], summary="Todas las versiones del límite, nunca sobrescritas")
def versions(sources: SourcesDep, ingrediente: str, cultivo: str, mercado: str):
    found = sources.limits.versions(ingrediente, cultivo, mercado)
    return [VersionOut.of(v) for v in sorted(found, key=lambda v: (v.applies_from is None, v.applies_from))]


@router.get("/proximos", response_model=list[VersionOut], summary="Versiones aprobadas que aún no aplican")
def next_versions(sources: SourcesDep, ingrediente: str, cultivo: str, mercado: str, fecha: date | None = None):
    return [VersionOut.of(v) for v in upcoming(sources.limits, ingrediente, cultivo, mercado, fecha or date.today())]
