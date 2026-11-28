"""Lab results of a lot against the legal limits of a market and, optionally, a buyer profile.

Here the residues are measured, so the checks are exact: a value above the limit in force on the sampling day breaks
it; a residue detected where the market has a default or no tolerance breaks it too.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.compliance.limits import limit_on
from domain.compliance.models import Limit, LimitStatus
from domain.exposure.acute import AcuteIntake, acute_intakes
from domain.findings import Finding, Severity
from domain.ports import LimitSource, ToxicologySource

from .profiles import BuyerProfile


@dataclass(frozen=True)
class Measurement:
    ingredient: str
    value_mg_kg: float


@dataclass(frozen=True)
class LabResult:
    lot: str
    crop: str
    market: str
    sampled_on: date
    measurements: tuple[Measurement, ...]


def check_lab_result(result: LabResult, limits: LimitSource, profile: BuyerProfile | None = None,
                     toxicology: ToxicologySource | None = None) -> list[Finding]:
    findings: list[Finding] = []
    fractions: dict[str, float] = {}
    detected = [m for m in result.measurements if m.value_mg_kg > 0]
    for m in detected:
        lim = limit_on(limits, m.ingredient, result.crop, result.market, result.sampled_on)
        ev = {"measured_mg_kg": m.value_mg_kg, "status": lim.status.value, "value_mg_kg": lim.value_mg_kg,
              "regulation": lim.regulation, "snapshot": lim.snapshot}
        common = {"ingredient": m.ingredient, "market": result.market, "evidence": ev}
        if lim.status is LimitStatus.NO_DATA:
            findings.append(Finding("MARKET_NOT_LOADED", Severity.INFO, lim.note, **common))
        elif lim.status is LimitStatus.WITHOUT_VALUE:
            findings.append(Finding("LIMIT_WITHOUT_VALUE", Severity.RISK,
                                    f"{m.ingredient}: no hay valor con el que comparar en {result.market}; {lim.note}",
                                    **common))
        elif lim.status is LimitStatus.NOT_PERMITTED:
            findings.append(Finding("RESIDUE_NOT_PERMITTED", Severity.BLOCKING,
                                    f"{m.ingredient}: {m.value_mg_kg} mg/kg sin tolerancia en {result.market}", **common))
        elif lim.value_mg_kg is not None:
            fraction = m.value_mg_kg / lim.value_mg_kg
            fractions[m.ingredient] = fraction
            ev["fraction_of_mrl"] = round(fraction, 4)
            if m.value_mg_kg > lim.value_mg_kg:
                findings.append(Finding("MRL_EXCEEDED", Severity.BLOCKING,
                                        f"{m.ingredient}: {m.value_mg_kg} mg/kg supera el LMR de {lim.value_mg_kg} "
                                        f"mg/kg en {result.market}", **common))
            elif profile and profile.max_fraction_of_mrl_per_substance is not None \
                    and fraction > profile.max_fraction_of_mrl_per_substance:
                findings.append(Finding("PROFILE_SUBSTANCE", Severity.BLOCKING,
                                        f"{m.ingredient}: {fraction:.0%} del LMR; {profile.name} acepta hasta "
                                        f"{profile.max_fraction_of_mrl_per_substance:.0%}", **common))
    if profile:
        findings += _profile_totals(result, profile, detected, fractions)
        if profile.max_fraction_of_arfd is not None:
            findings += _profile_arfd(result, profile, detected, toxicology)
    return findings


def _profile_totals(result: LabResult, profile: BuyerProfile, detected: list[Measurement],
                    fractions: dict[str, float]) -> list[Finding]:
    out: list[Finding] = []
    base = {"market": result.market}
    if profile.max_sum_of_mrl_fractions is not None:
        total = sum(fractions.values())
        if total > profile.max_sum_of_mrl_fractions:
            out.append(Finding("PROFILE_SUM", Severity.BLOCKING,
                               f"Suma de fracciones del LMR {total:.0%}; {profile.name} acepta hasta "
                               f"{profile.max_sum_of_mrl_fractions:.0%}", **base,
                               evidence={"sum": round(total, 4), "fractions": {k: round(v, 4) for k, v in fractions.items()}}))
    if profile.max_number_of_residues is not None and len(detected) > profile.max_number_of_residues:
        out.append(Finding("PROFILE_COUNT", Severity.BLOCKING,
                           f"{len(detected)} residuos detectados; {profile.name} acepta hasta "
                           f"{profile.max_number_of_residues}", **base, evidence={"detected": len(detected)}))
    return out


def _profile_arfd(result: LabResult, profile: BuyerProfile, detected: list[Measurement],
                  toxicology: ToxicologySource | None) -> list[Finding]:
    """Acute intake of each residue against its ARfD, for the most critical population (EFSA PRIMo 3.1)."""
    base = {"market": result.market}
    limit = profile.max_fraction_of_arfd
    consumption = toxicology.acute_consumption(result.crop) if toxicology else []
    if not consumption:
        return [Finding("PROFILE_ARFD_NOT_CHECKED", Severity.INFO,
                        f"{profile.name} pide exposición aguda bajo el {limit:.0%} de la ARfD; no hay datos de "
                        f"consumo cargados para {result.crop}", **base)]
    out, unknown = [], []
    for m in detected:
        arfd = toxicology.arfd(m.ingredient)
        if arfd is None or arfd.status == "not_set":
            unknown.append(m.ingredient)
            continue
        if arfd.status == "not_needed":
            continue
        worst = acute_intakes(m.value_mg_kg, arfd.value_mg_kg_bw, consumption)[0]
        evidence = {"measured_mg_kg": m.value_mg_kg, "arfd_mg_kg_bw": arfd.value_mg_kg_bw, "arfd_source": arfd.source,
                    "population": worst.population, "diet": worst.diet, "case": worst.case,
                    "iesti_mg_kg_bw": round(worst.iesti_mg_kg_bw, 6), "percent_of_arfd": round(worst.percent_of_arfd, 1)}
        if worst.percent_of_arfd > 100 * limit:
            out.append(Finding("PROFILE_ARFD", Severity.BLOCKING,
                               f"{m.ingredient}: ingesta aguda del {worst.percent_of_arfd:.0f} % de la ARfD "
                               f"({worst.population}, dieta {worst.diet}); {profile.name} acepta hasta {limit:.0%}",
                               ingredient=m.ingredient, evidence=evidence, **base))
    if unknown:
        out.append(Finding("PROFILE_ARFD_NOT_CHECKED", Severity.INFO,
                           "Sin ARfD fijada en la UE para: " + ", ".join(unknown), **base,
                           evidence={"ingredients": unknown}))
    return out


@dataclass(frozen=True)
class MeasurementAssessment:
    """One measured residue read against its limit and, when there is consumption data, its acute reference dose."""

    ingredient: str
    measured_mg_kg: float
    limit: Limit
    fraction_of_mrl: float | None         # measured / limit, when the limit has a value
    arfd_status: str | None                # set, not_needed, not_set; None without toxicology data
    arfd_mg_kg_bw: float | None
    acute: AcuteIntake | None              # most critical population


def assess_measurements(result: LabResult, limits: LimitSource,
                        toxicology: ToxicologySource | None = None) -> list[MeasurementAssessment]:
    consumption = toxicology.acute_consumption(result.crop) if toxicology else []
    out = []
    for m in result.measurements:
        lim = limit_on(limits, m.ingredient, result.crop, result.market, result.sampled_on)
        fraction = m.value_mg_kg / lim.value_mg_kg if lim.value_mg_kg else None
        arfd = toxicology.arfd(m.ingredient) if toxicology else None
        acute = None
        if arfd and arfd.status == "set" and consumption and m.value_mg_kg > 0:
            acute = acute_intakes(m.value_mg_kg, arfd.value_mg_kg_bw, consumption)[0]
        out.append(MeasurementAssessment(m.ingredient, m.value_mg_kg, lim, fraction,
                                         (arfd.status if arfd else ("not_set" if toxicology else None)),
                                         arfd.value_mg_kg_bw if arfd else None, acute))
    return out
