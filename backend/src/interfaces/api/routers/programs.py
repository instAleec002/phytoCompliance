"""Validation of a phytosanitary program and its safe harvest dates, and the import of a field sheet into a program."""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from domain.harvest.preharvest import safe_harvest
from domain.validation.program import validate_program

from ..schemas.common import FindingOut, verdict
from ..schemas.programs import (
    ApplicationIn,
    BlockIn,
    DoseCheckOut,
    ImportIn,
    ImportOut,
    ImportRowOut,
    ProgramIn,
    ReportOut,
    SafeHarvestOut,
)
from ..security import AccountsDep, UserDep
from ..sources import Sources, SourcesDep

router = APIRouter(tags=["programas"])

MAX_HOJA = 5_000_000            # bytes of a field sheet
ESTADOS = {"resuelta_por_nombre": "resolved_by_trade_name", "resuelta_por_ingrediente": "resolved_by_ingredient",
           "no_plaguicida": "not_a_pesticide", "necesita_persona": "needs_review"}
DOSIS = {"dentro": "within", "fuera_de_rango": "outside_range", "no_comparable": "not_comparable"}
OBJETIVO = {"registrado": "registered", "no_registrado": "not_registered", "sin_resolver": "unresolved"}


def _safe_harvest(program, sources: Sources) -> list[SafeHarvestOut]:
    out = []
    for block in program.blocks:
        s = safe_harvest(block.key, program.crop, list(program.applications), sources.registry)
        out.append(SafeHarvestOut(block=block.key, safe_from=s.safe_from,
                                  limiting_product=s.limiting.product_id if s.limiting else None,
                                  undetermined_by=[a.product_id for a in s.unknown]))
    return out


@router.post("/validar", response_model=ReportOut,
             summary="Valida un programa por bloque y mercado: registro, carencia, límites y rotación")
def validate(sources: SourcesDep, body: ProgramIn, principal: UserDep, acc: AccountsDep):
    program = body.to_domain()
    report = validate_program(program, sources.registry, sources.limits, sources.moa)
    acc.audit(principal.user.id, "programa_validado", {
        "cultivo": program.crop, "bloques": len(program.blocks), "aplicaciones": len(program.applications),
        "veredicto": verdict(report.findings), "hallazgos": len(report.findings)})
    return ReportOut(verdict=verdict(report.findings), findings=[FindingOut.of(f) for f in report.findings],
                     safe_harvest=_safe_harvest(program, sources))


@router.post("/cosecha-segura", response_model=list[SafeHarvestOut],
             summary="Primer día de cosecha que respeta las carencias de cada bloque")
def harvest(sources: SourcesDep, body: ProgramIn):
    return _safe_harvest(body.to_domain(), sources)


@lru_cache(maxsize=1)
def _aliases():
    from knowledge.normalization.ingredients import Aliases

    return Aliases.load()


@dataclass
class Importador:
    resolvedor: object           # knowledge.programs.resolver.Resolvedor
    graph: object                # where the registered doses are read; None skips the dose check


def importador(sources: SourcesDep) -> Importador:
    from knowledge.programs.resolver import Resolvedor

    graph = sources.limits.graph
    return Importador(Resolvedor(graph, sources.registry, _aliases()), graph)


ImportadorDep = Annotated[Importador, Depends(importador)]


def _texto(v) -> str:
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


@router.post("/programas/importar", response_model=ImportOut,
             summary="Lee una hoja de campo (Excel o CSV) y resuelve cada fila en un producto registrado y una fecha")
def import_program(body: ImportIn, imp: ImportadorDep, principal: UserDep, acc: AccountsDep):
    from knowledge.programs.importer import importar
    from knowledge.programs.sheets import HojaInvalida, leer_hoja

    try:
        contenido = base64.b64decode(body.file_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "file_base64 no es base64 válido") from None
    if len(contenido) > MAX_HOJA:
        raise HTTPException(413, f"la hoja supera {MAX_HOJA // 1_000_000} MB")
    try:
        filas = leer_hoja(contenido, body.file_name)
    except HojaInvalida as e:
        raise HTTPException(400, str(e)) from None
    r = importar(filas, nombre=body.name, cultivo=body.crop, mercados=body.markets, cosecha=body.harvest_on,
                 resolvedor=imp.resolvedor, plaga=body.pest_text, graph=imp.graph)
    acc.audit(principal.user.id, "programa_importado", {"cultivo": body.crop, **r.resumen})
    rows = []
    for x in r.filas:
        f, d = x.resolucion, x.dosis
        rows.append(ImportRowOut(
            n=x.n, original={k: _texto(v) for k, v in x.original.items()}, status=ESTADOS[x.estado], block=x.bloque,
            product_id=f.producto, trade_name=f.nombre_producto, ingredients=list(f.ingredientes),
            candidates=f.candidatos, applied_on=f.fecha, approximate_date=x.fecha_aproximada, pest=f.plaga,
            mismatch=f.discrepancia, notes=f.notas,
            dose=None if d is None else DoseCheckOut(text=None if d.texto is None else str(d.texto),
                                                     status=DOSIS[d.estado], reason=d.motivo, registered=d.registradas),
            target_pests=list(f.objetivo_plagas), target_check=OBJETIVO.get(f.registro_objetivo)))
    program = None
    if r.programa:
        p = r.programa
        program = ProgramIn(crop=p.crop, blocks=[BlockIn(key=b.key, harvest_on=b.harvest_on, markets=list(b.markets))
                                                 for b in p.blocks],
                            applications=[ApplicationIn(block=a.block, product_id=a.product_id, applied_on=a.applied_on,
                                                        pest=a.pest) for a in p.applications])
    return ImportOut(summary=r.resumen, rows=rows, program=program)
