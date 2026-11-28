"""Crops, markets, pests and registered products."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CropOut(BaseModel):
    key: str
    name_es: str | None = None
    scientific_name: str | None = None
    eu_code: str | None = None
    us_crop_group: str | None = None
    sigia_id: str | None = None


class MarketOut(BaseModel):
    key: str
    name: str | None = None
    source: str | None = None
    known_from: date | None = None


class PestOut(BaseModel):
    key: str
    scientific_name: str | None = None
    common_name: str | None = None
    other_use: bool = False
    products: int


class ProductOut(BaseModel):
    product_id: str
    trade_name: str | None = None
    registration_number: str | None = None
    product_type: str | None = None
    preharvest_interval_days: int | None = None
    preharvest_not_applicable: bool = False
    peru_mrl_mg_kg: float | None = None
    ingredients: list[str]
    snapshot: str | None = None


class IngredientOut(BaseModel):
    key: str
    biological: bool = False
    markets: list[str] = []
