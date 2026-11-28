"""HTTP API of the exact core. The web frontend and the desktop app (Tauri) use only this API (ADR 0001 of the
frontend). Every figure comes from the domain rules over the graph; the API produces none.

Run (from backend/):
    uv run uvicorn interfaces.api.app:app --reload
Documentation: /api/docs (OpenAPI at /api/openapi.json).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from accounts.credentials import WeakPassword
from accounts.service import AccountError, AuthFailed, NotFound
from shared.settings import Settings, settings

from .routers import admin, alerts, assistant, auth, catalog, lab, limits, mine, programs
from .security import current_user

DESCRIPTION = """Reglas exactas de cumplimiento fitosanitario: límites vigentes por mercado y fecha, validación de
programas por bloque, resultados de laboratorio contra perfiles de comprador y alertas de límites próximos. Cada
respuesta cita su norma y la instantánea de la fuente."""


def create_app(config: Settings = settings) -> FastAPI:
    app = FastAPI(title="TP202620505 · Núcleo de cumplimiento", version="0.1.0", description=DESCRIPTION,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(AccountError)
    def account_error(request: Request, exc: AccountError):
        code = 401 if isinstance(exc, AuthFailed) else 404 if isinstance(exc, NotFound) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.exception_handler(WeakPassword)
    def weak_password(request: Request, exc: WeakPassword):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/salud", tags=["servicio"], summary="El servicio responde (sin sesión)")
    def health():
        return {"status": "ok"}

    public = APIRouter(prefix="/api")
    public.include_router(auth.public)
    app.include_router(public)

    signed_in = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
    for router in (auth.private, mine.router, admin.router, catalog.router, limits.router, programs.router,
                   lab.router, alerts.router, assistant.router):
        signed_in.include_router(router)
    app.include_router(signed_in)
    return app


app = create_app()
