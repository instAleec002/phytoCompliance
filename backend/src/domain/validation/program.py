"""Validator of a phytosanitary program, by block and by destination market.

For each application it checks, in this order:
1. the product is registered by SENASA for the crop (and the pest, when given);
2. the pre-harvest interval is met by the planned harvest of the block;
3. for every ingredient and market, which limit applies on the harvest day: a market default or no tolerance means
   any detectable residue breaks it.
Then, per block, the mode-of-action rotation. The validator cannot know the residue the fruit will carry: what depends
on it is a risk, what breaks a registration or an interval is blocking.
"""
from __future__ import annotations

from domain.compliance.limits import limit_on
from domain.compliance.models import LimitStatus
from domain.findings import Finding, Severity
from domain.harvest.preharvest import check as check_interval
from domain.ports import LimitSource, ModeOfActionSource, RegistrySource
from domain.rotation.sequence import check_rotation

from .models import Application, Program, Report


def validate_program(program: Program, registry: RegistrySource, limits: LimitSource,
                     moa: ModeOfActionSource) -> Report:
    report = Report()
    for app in sorted(program.applications, key=lambda a: (a.block, a.applied_on)):
        report.findings += _check_application(program, app, registry, limits)
    for block in program.blocks:
        report.findings += check_rotation(block.key, list(program.applications), registry, moa)
    return report


def _check_application(program: Program, app: Application, registry: RegistrySource,
                       limits: LimitSource) -> list[Finding]:
    block = program.block(app.block)
    if block is None:
        return [Finding("UNKNOWN_BLOCK", Severity.BLOCKING, f"La aplicación indica el bloque {app.block}, que no está "
                        "en el programa", block=app.block, product_id=app.product_id)]
    where = {"block": block.key, "product_id": app.product_id}

    reg = registry.registration(app.product_id, program.crop, app.pest)
    if reg is None:
        product = registry.product(app.product_id)
        name = product.trade_name if product else app.product_id
        target = f" contra la plaga {app.pest}" if app.pest else ""
        return [Finding("NOT_REGISTERED", Severity.BLOCKING,
                        f"{name} no tiene registro en SENASA para {program.crop}{target}", **where)]

    findings: list[Finding] = []
    if app.applied_on > block.harvest_on:
        findings.append(Finding("APPLIED_AFTER_HARVEST", Severity.BLOCKING,
                                f"La aplicación del {app.applied_on:%d/%m/%Y} es posterior a la cosecha", **where))

    interval = check_interval(app, program.crop, registry)
    met = interval.met_on(block.harvest_on)
    if met is None:
        findings.append(Finding("PHI_UNKNOWN", Severity.RISK,
                                f"{reg.trade_name} no tiene período de carencia registrado para {program.crop}",
                                **where, evidence={"snapshot": reg.snapshot}))
    elif not met:
        findings.append(Finding(
            "PHI_NOT_MET", Severity.BLOCKING,
            f"{reg.trade_name}: carencia de {interval.interval_days} días; aplicado el {app.applied_on:%d/%m/%Y}, "
            f"la cosecha del {block.harvest_on:%d/%m/%Y} debe esperar hasta el {interval.safe_from:%d/%m/%Y}",
            **where, evidence={"interval_days": interval.interval_days, "safe_from": interval.safe_from.isoformat(),
                               "snapshot": reg.snapshot}))

    for ingredient in reg.ingredients:
        for market in block.markets:
            findings += _check_limit(ingredient, program.crop, market, block.harvest_on, reg.biological, limits, where)
    return findings


def _check_limit(ingredient, crop, market, day, biological, limits: LimitSource, where: dict) -> list[Finding]:
    lim = limit_on(limits, ingredient, crop, market, day)
    ev = {"status": lim.status.value, "value_mg_kg": lim.value_mg_kg, "regulation": lim.regulation,
          "residue": lim.residue, "snapshot": lim.snapshot, "day": day.isoformat()}
    common = {**where, "ingredient": ingredient, "market": market, "evidence": ev}
    out: list[Finding] = []
    if lim.status is LimitStatus.NO_DATA:
        out.append(Finding("MARKET_NOT_LOADED", Severity.INFO, lim.note, **common))
    elif lim.status is LimitStatus.DEFAULT:
        severity = Severity.INFO if biological else Severity.RISK
        out.append(Finding("DEFAULT_LIMIT", severity,
                           f"{ingredient}: sin LMR específico en {market} para {crop}; rige {lim.value_mg_kg} mg/kg, "
                           "cualquier residuo detectable lo incumple", **common))
    elif lim.status is LimitStatus.NOT_PERMITTED:
        severity = Severity.INFO if biological else Severity.RISK
        out.append(Finding("NOT_PERMITTED", severity,
                           f"{ingredient}: sin tolerancia en {market} para {crop}; el residuo no está permitido",
                           **common))
    elif lim.status is LimitStatus.WITHOUT_VALUE:
        out.append(Finding("LIMIT_WITHOUT_VALUE", Severity.RISK,
                           f"{ingredient}: {market} lista el residuo para {crop} sin valor; {lim.note}", **common))
    elif lim.status is LimitStatus.SPECIFIC and lim.at_limit_of_determination:
        out.append(Finding("LIMIT_AT_LOQ", Severity.RISK,
                           f"{ingredient}: el LMR en {market} es el límite de determinación ({lim.value_mg_kg} mg/kg)",
                           **common))
    if lim.ambiguous:
        out.append(Finding("AMBIGUOUS_RESIDUE", Severity.INFO,
                           f"{ingredient}: varias definiciones de residuo podrían aplicar en {market}; "
                           f"se usa la más estricta ({lim.value_mg_kg} mg/kg)", **common))
    return out
