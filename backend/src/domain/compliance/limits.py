"""Which limit applies to an ingredient, in a crop and market, on a given day.

Market rules:
- EU: when no specific limit applies, the default of 0.01 mg/kg holds (Regulation (EC) 396/2005, art. 18(1)(b));
  a substance in Annex IV needs no limit (exempt).
- US: without a tolerance in 40 CFR Part 180 the residue is not permitted; there is no default.
- CODEX: a reference standard; without a Codex limit there is no reference and the importing country decides.
- A market whose source is not loaded yet answers ``NO_DATA``: never a guess.
A version in force with no value and no exemption (EU fosetyl since Reg. (EU) 2024/2619: "the MRL for phosphonic acid
applies") is answered ``WITHOUT_VALUE`` with its footnote: neither the default nor a figure is assumed.
When several EU residues could apply (mineral oil: five paraffin oils by CAS number), the strictest limit is used and
the answer is marked ambiguous.
"""
from __future__ import annotations

from datetime import date

from domain.ports import LimitSource

from .models import Limit, LimitStatus, MrlRecord

DEFAULTS_MG_KG = {"EU": 0.01}
REFERENCE_MARKETS = {"CODEX"}
EU_DEFAULT_RULE = "Reglamento (CE) 396/2005, art. 18(1)(b): valor por defecto de 0,01 mg/kg"


def limit_on(source: LimitSource, ingredient: str, crop: str, market: str, day: date) -> Limit:
    base = {"ingredient": ingredient, "crop": crop, "market": market, "day": day}
    if market not in source.loaded_markets():
        return Limit(**base, status=LimitStatus.NO_DATA, value_mg_kg=None, at_limit_of_determination=False,
                     regulation=None, residue=None, snapshot=None, note=f"Los LMR de {market} aún no están cargados")

    known = source.known_from(market)
    if known is not None and day < known:
        return Limit(**base, status=LimitStatus.NO_DATA, value_mg_kg=None, at_limit_of_determination=False,
                     regulation=None, residue=None, snapshot=None,
                     note=f"Para {market} solo se conoce el estado vigente al {known:%d/%m/%Y}")

    info = source.ingredient(ingredient, market)
    in_force = [v for v in source.versions(ingredient, crop, market) if v.in_force_on(day)]

    if not in_force:
        reason = info.absence_reason
        if reason is None and info.residues and not source.versions(ingredient, crop, market):
            reason = f"{market} lista el residuo ({', '.join(info.residues)}) pero sin límite para este cultivo"
        return _without_specific_limit(base, market, reason)

    exempt = [v for v in in_force if v.no_mrl_required]
    numeric = [v for v in in_force if v.value_mg_kg is not None]
    if exempt and not numeric:
        v = exempt[0]
        return Limit(**base, status=LimitStatus.EXEMPT, value_mg_kg=None, at_limit_of_determination=False,
                     regulation=v.regulation, residue=v.residue, snapshot=v.snapshot,
                     ambiguous=len({e.residue for e in exempt}) > 1, note=v.footnote, candidates=tuple(in_force))

    if not numeric:
        v = in_force[0]
        return Limit(**base, status=LimitStatus.WITHOUT_VALUE, value_mg_kg=None, at_limit_of_determination=False,
                     regulation=v.regulation, residue=v.residue, snapshot=v.snapshot,
                     note=v.footnote or "La fuente lista el residuo para este cultivo sin valor ni exención",
                     candidates=tuple(in_force))

    strictest = min(numeric, key=lambda v: v.value_mg_kg)
    residues = {v.residue for v in numeric}
    return Limit(**base, status=LimitStatus.SPECIFIC, value_mg_kg=strictest.value_mg_kg,
                 at_limit_of_determination=strictest.at_limit_of_determination, regulation=strictest.regulation,
                 residue=strictest.residue, snapshot=strictest.snapshot, ambiguous=len(residues) > 1,
                 note="Varios residuos podrían aplicar; se usa el límite más estricto" if len(residues) > 1 else None,
                 candidates=tuple(in_force))


def _without_specific_limit(base: dict, market: str, reason: str | None) -> Limit:
    if market in DEFAULTS_MG_KG:
        return Limit(**base, status=LimitStatus.DEFAULT, value_mg_kg=DEFAULTS_MG_KG[market], at_limit_of_determination=True,
                     regulation=EU_DEFAULT_RULE if market == "EU" else None, residue=None, snapshot=None,
                     note=reason or "Sin límite específico vigente para este cultivo")
    if market in REFERENCE_MARKETS:
        return Limit(**base, status=LimitStatus.NO_REFERENCE, value_mg_kg=None, at_limit_of_determination=False,
                     regulation=None, residue=None, snapshot=None,
                     note=reason or f"{market} no fija límite: rige el del país de destino")
    return Limit(**base, status=LimitStatus.NOT_PERMITTED, value_mg_kg=None, at_limit_of_determination=False,
                 regulation=None, residue=None, snapshot=None,
                 note=reason or f"Sin tolerancia en {market}: el residuo no está permitido")


def upcoming(source: LimitSource, ingredient: str, crop: str, market: str, day: date) -> list[MrlRecord]:
    """Versions approved but not applicable yet on ``day`` (their application date is later)."""
    if market not in source.loaded_markets():
        return []
    return sorted((v for v in source.versions(ingredient, crop, market) if v.applies_from and v.applies_from > day),
                  key=lambda v: v.applies_from)
