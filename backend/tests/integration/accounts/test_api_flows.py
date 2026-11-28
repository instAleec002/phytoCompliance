"""Admin and user flows through the HTTP API, over the local PostgreSQL in a throwaway schema. Skipped when the database
is not running (make db)."""
import pytest
from fastapi.testclient import TestClient

from accounts.service import Accounts
from interfaces.api.app import create_app
from interfaces.api.security import accounts
from interfaces.api.sources import graph_sources
from shared.settings import Settings, get_settings

from ...unit.interfaces.api.test_api import fake_sources
from .test_service import PASSWORD, schema  # noqa: F401  (schema is a fixture)

ANA_PASSWORD = "clave-de-prueba-ana-1"


@pytest.fixture
def app(schema):  # noqa: F811
    acc = Accounts(schema)
    acc.create_admin("andrea@example.org", "andrea", "Andrea", PASSWORD)
    config = Settings(_env_file=None, api_web_url="https://tp.example.org")
    application = create_app(config)
    application.dependency_overrides[get_settings] = lambda: config
    application.dependency_overrides[accounts] = lambda: Accounts(schema)
    application.dependency_overrides[graph_sources] = fake_sources
    return application


def sign_in(client, ident, password):
    r = client.post("/api/auth/iniciar-sesion", json={"identificador": ident, "contrasena": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_admin_invites_and_the_user_works(app):
    c = TestClient(app)
    assert c.get("/api/cultivos").status_code == 401
    admin = sign_in(c, "andrea", PASSWORD)
    assert c.get("/api/auth/yo", headers=admin).json()["rol"] == "admin"

    # invite: the link points to the interface and is shown once
    r = c.post("/api/admin/usuarios", headers=admin,
               json={"email": "ana@example.org", "usuario": "ana", "nombre": "Ana Quispe", "rol": "usuario"})
    assert r.status_code == 201
    link = r.json()["enlace"]
    assert link.startswith("https://tp.example.org/activar/?t=")
    token = link.split("t=", 1)[1]

    # activation
    assert c.post("/api/auth/enlace", json={"token": token}).json()["usuario"] == "ana"
    notice = c.get("/api/auth/aviso-privacidad").json()
    weak = c.post("/api/auth/activar", json={"token": token, "contrasena": "corta", "aviso_version": notice["version"]})
    assert weak.status_code == 400 and "12" in weak.json()["detail"]
    no_notice = c.post("/api/auth/activar", json={"token": token, "contrasena": ANA_PASSWORD})
    assert no_notice.status_code == 400 and "aviso" in no_notice.json()["detail"]
    ok = {"token": token, "contrasena": ANA_PASSWORD, "aviso_version": notice["version"]}
    activated = c.post("/api/auth/activar", json=ok)
    assert activated.status_code == 200 and activated.json()["aviso_pendiente"] is False
    assert c.post("/api/auth/activar", json=ok).status_code == 400

    # the user signs in with the email as well, works and saves
    ana = sign_in(c, "ana@example.org", ANA_PASSWORD)
    assert c.get("/api/cultivos", headers=ana).status_code == 200
    assert c.get("/api/admin/usuarios", headers=ana).status_code == 403
    draft = {"crop": "blueberry", "blocks": [{"key": "A1"}], "applications": []}
    p = c.post("/api/mis/programas", headers=ana, json={"nombre": "Campaña", "cultivo": "blueberry", "contenido": draft})
    assert p.status_code == 201
    pid = p.json()["id"]
    assert [x["nombre"] for x in c.get("/api/mis/programas", headers=ana).json()] == ["Campaña"]

    # the admin reads the user's work, but has no route to change it
    ana_id = r.json()["usuario"]["id"]
    assert c.get(f"/api/admin/usuarios/{ana_id}/programas/{pid}", headers=admin).json()["contenido"] == draft
    assert c.put(f"/api/mis/programas/{pid}", headers=admin,
                 json={"nombre": "x", "cultivo": "blueberry", "contenido": draft}).status_code == 404
    assert {a["accion"] for a in c.get("/api/admin/auditoria", headers=admin).json()} >= {
        "usuario_invitado", "cuenta_activada", "programa_guardado"}

    # deactivation cuts the session at once
    assert c.patch(f"/api/admin/usuarios/{ana_id}", headers=admin, json={"estado": "desactivado"}).status_code == 200
    assert c.get("/api/cultivos", headers=ana).status_code == 401


def test_sign_in_failures_and_sign_out(app):
    c = TestClient(app)
    bad = c.post("/api/auth/iniciar-sesion", json={"identificador": "andrea", "contrasena": "mala-clave-000"})
    unknown = c.post("/api/auth/iniciar-sesion", json={"identificador": "nadie", "contrasena": "mala-clave-000"})
    assert bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json()
    admin = sign_in(c, "ANDREA", PASSWORD)
    [s] = c.get("/api/mis/sesiones", headers=admin).json()
    assert s["actual"] is True
    assert c.post("/api/auth/cerrar-sesion", headers=admin).status_code == 204
    assert c.get("/api/auth/yo", headers=admin).status_code == 401


def test_last_admin_cannot_demote_itself(app):
    c = TestClient(app)
    admin = sign_in(c, "andrea", PASSWORD)
    me = c.get("/api/auth/yo", headers=admin).json()
    r = c.patch(f"/api/admin/usuarios/{me['id']}", headers=admin, json={"rol": "usuario"})
    assert r.status_code == 400 and "administrador" in r.json()["detail"]
