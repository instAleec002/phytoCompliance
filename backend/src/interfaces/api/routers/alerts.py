"""Early alerts: limits published that apply later, for one ingredient or for every ingredient of a program."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from domain.alerts.upcoming import alerts_for, alerts_for_program

from ..schemas.alerts import AlertOut
from ..schemas.programs import ProgramIn
from ..sources import SourcesDep

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("", response_model=list[AlertOut], summary="Límites próximos de un ingrediente")
def alerts(sources: SourcesDep, ingrediente: str, cultivo: str, mercado: str, fecha: date | None = None,
           horizonte_dias: int | None = Query(default=None, ge=1)):
    today = fecha or date.today()
    return [AlertOut.of(a, today)
            for a in alerts_for(sources.limits, ingrediente, cultivo, mercado, today, horizonte_dias)]


@router.post("/programa", response_model=list[AlertOut],
             summary="Límites próximos de los ingredientes de un programa, con los bloques afectados")
def program_alerts(sources: SourcesDep, body: ProgramIn, fecha: date | None = None):
    today = fecha or date.today()
    return [AlertOut.of(a, today)
            for a in alerts_for_program(body.to_domain(), sources.registry, sources.limits, today)]
