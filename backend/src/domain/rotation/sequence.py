"""Mode-of-action rotation: two consecutive applications on a block with an ingredient of the same FRAC, IRAC or HRAC
group raise the risk of resistance. The groups come from a :class:`ModeOfActionSource`; while they are not loaded,
the rule says the rotation could not be checked instead of passing it.

Groups are compared only within one scheme ("FRAC:11" against "FRAC:11"). Groups without one specific mode of action
are left out of the consecutive check: FRAC multi-site (M), biologicals with multiple modes (BM), not classified (NC)
and unknown (U); IRAC unknown or uncertain (UN, UNB, UNE, UNF, UNM); HRAC unknown (0).
"""
from __future__ import annotations

import re

from domain.findings import Finding, Severity
from domain.ports import ModeOfActionSource, RegistrySource
from domain.validation.models import Application

NON_SPECIFIC = {"FRAC": re.compile(r"^(?:(?:M|BM|U)\d+|NC)$"), "IRAC": re.compile(r"^UN[A-Z]?$"),
                "HRAC": re.compile(r"^0$")}
MAX_CONSECUTIVE = 1                 # applications of one group in a row before a finding


def specific(group: str) -> bool:
    scheme, _, code = group.partition(":")
    pattern = NON_SPECIFIC.get(scheme)
    return not (pattern and pattern.match(code))


def _groups(app: Application, registry: RegistrySource, moa: ModeOfActionSource) -> tuple[set[str], list[str]]:
    reg = registry.product(app.product_id)
    if reg is None:
        return set(), []
    groups, unknown = set(), []
    for ing in reg.ingredients:
        found = moa.groups(ing)
        if not found and not reg.biological:
            unknown.append(ing)
        groups |= {g for g in found if specific(g)}
    return groups, unknown


def check_rotation(block: str, applications: list[Application], registry: RegistrySource,
                   moa: ModeOfActionSource) -> list[Finding]:
    apps = sorted((a for a in applications if a.block == block), key=lambda a: a.applied_on)
    findings: list[Finding] = []
    unknown: dict[str, None] = {}
    previous: tuple[Application, set[str]] | None = None
    run: dict[str, int] = {}
    for app in apps:
        groups, missing = _groups(app, registry, moa)
        unknown.update(dict.fromkeys(missing))
        run = {g: run.get(g, 0) + 1 for g in groups}
        for g, n in run.items():
            if n > MAX_CONSECUTIVE and previous:
                findings.append(Finding(
                    "ROTATION_SAME_GROUP", Severity.RISK,
                    f"Aplicaciones consecutivas del grupo {g} ({previous[0].applied_on:%d/%m/%Y} y "
                    f"{app.applied_on:%d/%m/%Y}): conviene rotar el modo de acción",
                    block=block, product_id=app.product_id,
                    evidence={"group": g, "consecutive": n, "previous_product": previous[0].product_id}))
        previous = (app, groups)
    if unknown:
        findings.append(Finding(
            "ROTATION_NOT_CHECKED", Severity.INFO,
            "No se pudo revisar la rotación de: " + ", ".join(unknown) + " (grupo de modo de acción no cargado)",
            block=block, evidence={"ingredients": list(unknown)}))
    return findings
