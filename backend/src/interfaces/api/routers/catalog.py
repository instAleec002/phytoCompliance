"""Crops, markets, pests of a crop and products registered by SENASA."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas.catalog import CropOut, IngredientOut, MarketOut, PestOut, ProductOut
from ..sources import SourcesDep

router = APIRouter(tags=["catálogo"])


@router.get("/cultivos", response_model=list[CropOut], summary="Cultivos del alcance")
def crops(sources: SourcesDep):
    return sources.catalog.crops()


@router.get("/mercados", response_model=list[MarketOut],
            summary="Mercados cargados; known_from indica desde qué fecha se conoce su estado")
def markets(sources: SourcesDep):
    return sources.catalog.markets()


@router.get("/plagas", response_model=list[PestOut], summary="Plagas y otros usos con productos registrados")
def pests(sources: SourcesDep, cultivo: str = Query(examples=["blueberry"])):
    return sources.catalog.pests(cultivo)


@router.get("/productos", response_model=list[ProductOut],
            summary="Productos registrados en SENASA para un cultivo y una plaga")
def products(sources: SourcesDep, cultivo: str = Query(examples=["blueberry"]),
             plaga: str = Query(examples=["000626"])):
    return sources.catalog.products(cultivo, plaga)


@router.get("/ingredientes", response_model=list[IngredientOut],
            summary="Ingredientes para autocompletar: los del cultivo si se indica, filtrados por texto")
def ingredients(sources: SourcesDep, q: str | None = None, cultivo: str | None = None,
                limite: int = Query(default=50, ge=1, le=500)):
    return sources.catalog.ingredients(cultivo, q, limite)
