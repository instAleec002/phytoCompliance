"""Lab results against the legal limits and a buyer profile, and the profiles available."""
from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException, status

from domain.validation.profiles import BuyerProfile, load_profiles
from domain.validation.residues import assess_measurements, check_lab_result
from shared.settings import REPO

from ..schemas.common import FindingOut, verdict
from ..schemas.lab import LabReportOut, LabResultIn, MeasurementOut, ProfileOut
from ..security import AccountsDep, UserDep
from ..sources import SourcesDep

router = APIRouter(tags=["laboratorio"])
PROFILES_DIR = REPO / "backend" / "config" / "buyer_profiles"


@lru_cache
def profiles() -> dict[str, BuyerProfile]:
    return load_profiles(PROFILES_DIR)


@router.get("/perfiles", response_model=list[ProfileOut], summary="Perfiles de comprador configurados")
def list_profiles():
    return [ProfileOut(**p.__dict__) for p in profiles().values()]


@router.post("/laboratorio", response_model=LabReportOut,
             summary="Resultados de laboratorio de un lote contra el LMR y, si se indica, un perfil de comprador")
def lab(sources: SourcesDep, body: LabResultIn, principal: UserDep, acc: AccountsDep):
    """The evaluation is saved under the user (Mis lotes) with its input and result."""
    profile = None
    if body.profile:
        profile = profiles().get(body.profile)
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Perfil {body.profile} no configurado")
    lot = body.to_domain()
    findings = check_lab_result(lot, sources.limits, profile, sources.toxicology)
    rows = assess_measurements(lot, sources.limits, sources.toxicology)
    report = LabReportOut(verdict=verdict(findings), findings=[FindingOut.of(f) for f in findings],
                          measurements=[MeasurementOut.of(r) for r in rows])
    saved = acc.save_lot(principal.user.id, body.lot, body.crop, body.market, body.sampled_on, body.profile,
                         report.verdict, body.model_dump(mode="json"), report.model_dump(mode="json"))
    report.lot_id = saved["id"]
    return report
