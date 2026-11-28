"""Lab results of a lot, optionally against a buyer profile."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from domain.validation.residues import LabResult, Measurement, MeasurementAssessment

from .common import FindingOut
from .limits import LimitOut


class MeasurementIn(BaseModel):
    ingredient: str
    value_mg_kg: float = Field(ge=0)


class LabResultIn(BaseModel):
    lot: str
    crop: str
    market: str
    sampled_on: date
    measurements: list[MeasurementIn] = Field(min_length=1)
    profile: str | None = Field(default=None, description="Clave de config/buyer_profiles, p. ej. lidl_2025")

    def to_domain(self) -> LabResult:
        return LabResult(self.lot, self.crop, self.market, self.sampled_on,
                         tuple(Measurement(m.ingredient, m.value_mg_kg) for m in self.measurements))


class AcuteOut(BaseModel):
    population: str
    diet: str
    case: str
    iesti_mg_kg_bw: float
    percent_of_arfd: float


class MeasurementOut(BaseModel):
    ingredient: str
    measured_mg_kg: float
    limit: LimitOut
    fraction_of_mrl: float | None = Field(description="Medido / LMR, cuando el límite tiene valor")
    arfd_status: str | None = Field(description="set, not_needed o not_set; null sin datos toxicológicos")
    arfd_mg_kg_bw: float | None
    acute: AcuteOut | None = Field(description="Ingesta aguda de la población más crítica (EFSA PRIMo 3.1)")

    @classmethod
    def of(cls, a: MeasurementAssessment) -> MeasurementOut:
        acute = None if a.acute is None else AcuteOut(population=a.acute.population, diet=a.acute.diet,
                                                      case=a.acute.case, iesti_mg_kg_bw=a.acute.iesti_mg_kg_bw,
                                                      percent_of_arfd=a.acute.percent_of_arfd)
        return cls(ingredient=a.ingredient, measured_mg_kg=a.measured_mg_kg, limit=LimitOut.of(a.limit),
                   fraction_of_mrl=a.fraction_of_mrl, arfd_status=a.arfd_status, arfd_mg_kg_bw=a.arfd_mg_kg_bw,
                   acute=acute)


class LabReportOut(BaseModel):
    verdict: str | None
    findings: list[FindingOut]
    measurements: list[MeasurementOut]
    lot_id: int | None = Field(default=None, description="Id del lote guardado en Mis lotes")


class ProfileOut(BaseModel):
    key: str
    name: str
    max_fraction_of_mrl_per_substance: float | None
    max_sum_of_mrl_fractions: float | None
    max_number_of_residues: int | None
    max_fraction_of_arfd: float | None
