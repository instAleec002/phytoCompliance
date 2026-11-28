"""A phytosanitary program sent for validation, and what comes back."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from domain.validation.models import Application, Block, Program

from .common import FindingOut


class BlockIn(BaseModel):
    key: str = Field(examples=["A1"])
    harvest_on: date = Field(description="Cosecha planificada del bloque")
    markets: list[str] = Field(min_length=1, examples=[["EU", "US"]])


class ApplicationIn(BaseModel):
    block: str
    product_id: str = Field(description="Id del producto en SIGIA")
    applied_on: date
    pest: str | None = Field(default=None, description="Id de la plaga en SIGIA, o use:<clase> para otros usos")


class ProgramIn(BaseModel):
    crop: str = Field(examples=["blueberry"])
    blocks: list[BlockIn] = Field(min_length=1)
    applications: list[ApplicationIn]

    @model_validator(mode="after")
    def unique_blocks(self):
        keys = [b.key for b in self.blocks]
        if len(keys) != len(set(keys)):
            raise ValueError("cada bloque debe tener una clave distinta")
        return self

    def to_domain(self) -> Program:
        return Program(self.crop, tuple(Block(b.key, b.harvest_on, tuple(b.markets)) for b in self.blocks),
                       tuple(Application(a.block, a.product_id, a.applied_on, a.pest) for a in self.applications))


class SafeHarvestOut(BaseModel):
    block: str
    safe_from: date | None = Field(description="Primer día en que se puede cosechar respetando las carencias")
    limiting_product: str | None
    undetermined_by: list[str] = Field(description="Productos cuya carencia no se conoce")


class ReportOut(BaseModel):
    verdict: str | None = Field(description="La severidad más alta encontrada; null si no hay hallazgos")
    findings: list[FindingOut]
    safe_harvest: list[SafeHarvestOut]


class ImportIn(BaseModel):
    """A field sheet as the farm writes it, with what the sheet does not say: crop, markets and planned harvest."""
    name: str = Field(default="programa", max_length=120)
    crop: str = Field(examples=["avocado"])
    markets: list[str] = Field(min_length=1, examples=[["EU", "US"]])
    harvest_on: date = Field(description="Cosecha planificada: fija la campaña de las fechas sin año")
    pest_text: str | None = Field(default=None, max_length=200,
                                  description="Plaga del programa entero, como la escribe la hoja (p. ej. «oídio»)")
    file_name: str = Field(examples=["programa_palto.xlsx"], description="Con su extensión: .xlsx o .csv")
    file_base64: str = Field(description="Contenido del archivo en base64")


class DoseCheckOut(BaseModel):
    text: str | None
    status: str = Field(description="within, outside_range (para revisar, no bloquea) o not_comparable")
    reason: str | None = None
    registered: list[str] = Field(default_factory=list, description="Dosis registradas en SIGIA para ese uso")


class ImportRowOut(BaseModel):
    n: int
    original: dict[str, str] = Field(description="La fila tal como vino en la hoja")
    status: str = Field(description="resolved_by_trade_name, resolved_by_ingredient, not_a_pesticide o needs_review")
    block: str
    product_id: str | None
    trade_name: str | None
    ingredients: list[str]
    candidates: int = Field(description="Productos registrados que la fila podría ser")
    applied_on: date | None
    approximate_date: bool = Field(description="La fecha sale de una etapa o de un rango de meses")
    pest: str | None
    mismatch: str | None = Field(description="El nombre comercial y el ingrediente escrito no coinciden")
    notes: list[str]
    dose: DoseCheckOut | None
    target_pests: list[str] = Field(default_factory=list, description="Plagas de SIGIA que nombra la columna «objetivo»")
    target_check: str | None = Field(default=None, description="registered, not_registered (para revisar, no bloquea) "
                                                                "o unresolved; null si la fila no trae objetivo")


class ImportOut(BaseModel):
    summary: dict
    rows: list[ImportRowOut]
    program: ProgramIn | None = Field(description="Listo para /api/validar; null si ninguna fila se resolvió")
