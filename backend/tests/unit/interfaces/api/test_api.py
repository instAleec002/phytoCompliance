"""HTTP API over in-memory sources and accounts: sessions, CORS for the desktop app, and each endpoint. The accounts
themselves are tested over PostgreSQL in tests/integration/accounts."""
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from accounts.service import Session, User
from domain.ports import Arfd
from interfaces.api.app import create_app
from interfaces.api.security import accounts
from interfaces.api.sources import Sources, graph_sources
from shared.settings import Settings

from ...domain.fakes import PYRACLOSTROBIN, FakeLimits, FakeModeOfAction, FakeRegistry, mrl
from ...domain.test_acute import GRAPE_CHILD, FakeToxicology

TEST_TOKEN = "sesion-solo-para-pruebas"
NOW = datetime(2026, 10, 28, 9, tzinfo=UTC)
ANA = User(2, "ana@example.org", "ana", "Ana", "usuario", "activo", NOW, NOW)


class FakeAccounts:
    """Authenticates one test session and records what the routes save."""

    def __init__(self):
        self.audits, self.lots = [], []

    def authenticate(self, token):
        return (ANA, Session(7, ANA.id, NOW, NOW, NOW, "pytest")) if token == TEST_TOKEN else None

    def audit(self, user_id, action, detail=None):
        self.audits.append((user_id, action, detail))

    def save_lot(self, user_id, *args):
        self.lots.append((user_id, args))
        return {"id": len(self.lots), "creado": NOW}


class FakeCatalog:
    def crops(self):
        return [{"key": "blueberry", "name_es": "arándano", "eu_code": "0154010"}]

    def markets(self):
        return [{"key": "EU", "name": "Unión Europea"}, {"key": "US", "known_from": "2026-10-26"}]

    def pests(self, crop):
        return [{"key": "000626", "scientific_name": "Botrytis cinerea", "common_name": "Moho gris", "products": 2}]

    def products(self, crop, pest):
        return [{"product_id": "ADIKO", "trade_name": "ADIKO SC", "ingredients": ["pyraclostrobin"],
                 "preharvest_interval_days": 14}]

    def ingredients(self, crop=None, query=None, limit=50):
        rows = [{"key": "pyraclostrobin", "markets": ["CODEX", "EU", "US"]}, {"key": "tolfenpyrad", "markets": ["US"]}]
        return [r for r in rows if not query or query in r["key"]][:limit]


def fake_sources():
    limits = FakeLimits().add("pyraclostrobin", PYRACLOSTROBIN)
    limits.add("pyraclostrobin", PYRACLOSTROBIN, crop="table_grape")
    limits.add("x", [mrl("X", 0.5, date(2015, 1, 1), date(2027, 3, 1)), mrl("X", 0.01, date(2027, 3, 1))])
    registry = FakeRegistry().add("ADIKO", ["pyraclostrobin"], 14, name="ADIKO SC").add("PX", ["x"], 7)
    tox = FakeToxicology({"pyraclostrobin": Arfd(0.03, "set", "Reg. (EU) 2026/1976")}, {"table_grape": [GRAPE_CHILD]})
    yield Sources(limits=limits, registry=registry, moa=FakeModeOfAction({"pyraclostrobin": {"FRAC:11"}}),
                  toxicology=tox, catalog=FakeCatalog())


@pytest.fixture
def fake_accounts():
    return FakeAccounts()


@pytest.fixture
def client(fake_accounts):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[graph_sources] = fake_sources
    app.dependency_overrides[accounts] = lambda: fake_accounts
    return TestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"})


def test_health_needs_no_session():
    app = create_app(Settings(_env_file=None))
    assert TestClient(app).get("/api/salud").json() == {"status": "ok"}


def test_session_required_and_checked(client):
    assert client.get("/api/cultivos", headers={"Authorization": "Bearer otra"}).status_code == 401
    assert client.get("/api/cultivos", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/cultivos").status_code == 200


def test_admin_routes_refuse_a_normal_user(client):
    assert client.get("/api/admin/usuarios").status_code == 403


def test_cors_allows_the_desktop_app(client):
    response = client.options("/api/cultivos", headers={"Origin": "tauri://localhost",
                                                         "Access-Control-Request-Method": "GET"})
    assert response.headers.get("access-control-allow-origin") == "tauri://localhost"


def test_catalog(client):
    assert client.get("/api/cultivos").json()[0]["key"] == "blueberry"
    assert client.get("/api/mercados").json()[1]["known_from"] == "2026-10-26"
    assert client.get("/api/plagas", params={"cultivo": "blueberry"}).json()[0]["products"] == 2
    [p] = client.get("/api/productos", params={"cultivo": "blueberry", "plaga": "000626"}).json()
    assert p["trade_name"] == "ADIKO SC" and p["ingredients"] == ["pyraclostrobin"]


def test_limit_on_a_day(client):
    body = client.get("/api/lmr", params={"ingrediente": "pyraclostrobin", "cultivo": "blueberry", "mercado": "EU",
                                          "fecha": "2026-10-28"}).json()
    assert (body["status"], body["value_mg_kg"], body["regulation"]) == \
           ("specific", 4.0, "Commission Regulation (EU) 2026/140")
    default = client.get("/api/lmr", params={"ingrediente": "tolfenpyrad", "cultivo": "blueberry",
                                             "mercado": "EU", "fecha": "2026-10-28"}).json()
    assert (default["status"], default["value_mg_kg"]) == ("default", 0.01)


def test_versions_and_upcoming(client):
    versions = client.get("/api/lmr/versiones", params={"ingrediente": "pyraclostrobin", "cultivo": "blueberry",
                                                        "mercado": "EU"}).json()
    assert [v["value_mg_kg"] for v in versions] == [0.5, 4.0, 4.0, 4.0]
    upcoming = client.get("/api/lmr/proximos", params={"ingrediente": "x", "cultivo": "blueberry", "mercado": "EU",
                                                       "fecha": "2026-10-28"}).json()
    assert [u["applies_from"] for u in upcoming] == ["2027-03-01"]


PROGRAM = {"crop": "blueberry", "blocks": [{"key": "A", "harvest_on": "2026-12-01", "markets": ["EU"]}],
           "applications": [{"block": "A", "product_id": "ADIKO", "applied_on": "2026-11-20", "pest": "000626"}]}


def test_validate_program(client, fake_accounts):
    body = client.post("/api/validar", json=PROGRAM).json()
    assert fake_accounts.audits[-1][:2] == (ANA.id, "programa_validado")
    assert body["verdict"] == "blocking"
    assert [f["code"] for f in body["findings"]] == ["PHI_NOT_MET"]
    assert body["safe_harvest"] == [{"block": "A", "safe_from": "2026-12-04", "limiting_product": "ADIKO",
                                     "undetermined_by": []}]


def test_program_validation_errors(client):
    bad = {**PROGRAM, "blocks": PROGRAM["blocks"] * 2}
    assert client.post("/api/validar", json=bad).status_code == 422
    assert client.post("/api/validar", json={**PROGRAM, "blocks": []}).status_code == 422


def test_safe_harvest(client):
    [s] = client.post("/api/cosecha-segura", json=PROGRAM).json()
    assert s["safe_from"] == "2026-12-04"


def test_lab_with_profile_and_arfd(client, fake_accounts):
    lot = {"lot": "L-1", "crop": "table_grape", "market": "EU", "sampled_on": "2026-10-28", "profile": "lidl_2025",
           "measurements": [{"ingredient": "pyraclostrobin", "value_mg_kg": 1.0}]}
    body = client.post("/api/laboratorio", json=lot).json()
    codes = {f["code"]: f for f in body["findings"]}
    assert body["verdict"] == "blocking" and "PROFILE_ARFD" in codes
    assert codes["PROFILE_ARFD"]["evidence"]["percent_of_arfd"] == 243.1
    assert body["lot_id"] == 1 and fake_accounts.lots[0][0] == ANA.id      # saved in Mis lotes
    [row] = body["measurements"]
    assert (row["limit"]["status"], round(row["acute"]["percent_of_arfd"], 1)) == ("specific", 243.1)
    assert client.post("/api/laboratorio", json={**lot, "profile": "no_existe"}).status_code == 404
    assert client.post("/api/laboratorio", json={**lot, "measurements": []}).status_code == 422


def test_profiles(client):
    keys = {p["key"]: p for p in client.get("/api/perfiles").json()}
    assert keys["lidl_2025"]["max_number_of_residues"] == 5


def test_alerts(client):
    [a] = client.get("/api/alertas", params={"ingrediente": "x", "cultivo": "blueberry", "mercado": "EU",
                                             "fecha": "2026-10-28"}).json()
    assert (a["new_mg_kg"], a["days_left"], a["stricter"]) == (0.01, 124, True)
    program = {"crop": "blueberry",
               "blocks": [{"key": "late", "harvest_on": "2027-04-01", "markets": ["EU"]}],
               "applications": [{"block": "late", "product_id": "PX", "applied_on": "2027-02-01"}]}
    [b] = client.post("/api/alertas/programa", params={"fecha": "2026-10-28"}, json=program).json()
    assert b["blocks_affected"] == ["late"]


def test_openapi_lists_every_endpoint(client):
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert {"/api/cultivos", "/api/mercados", "/api/plagas", "/api/productos", "/api/lmr", "/api/lmr/versiones",
            "/api/lmr/proximos", "/api/validar", "/api/cosecha-segura", "/api/laboratorio", "/api/perfiles",
            "/api/alertas", "/api/alertas/programa", "/api/salud", "/api/ingredientes"} <= paths


def test_ingredients_for_autocomplete(client):
    assert [i["key"] for i in client.get("/api/ingredientes", params={"q": "pyrac"}).json()] == ["pyraclostrobin"]
    assert client.get("/api/ingredientes", params={"limite": 0}).status_code == 422


def test_import_field_sheet(fake_accounts):
    import base64

    from interfaces.api.routers.programs import Importador, importador
    from knowledge.programs.resolver import Resolvedor

    from ...knowledge.programs.fakes import FakeAliases, grafo

    g = grafo()
    reg = FakeRegistry().add("LORSBAN", ["chlorpyrifos"], 21, crop="table_grape").add("PIRIMOR", ["chlorpyrifos"], 7,
                                                                                    crop="table_grape")
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[graph_sources] = fake_sources
    app.dependency_overrides[accounts] = lambda: fake_accounts
    app.dependency_overrides[importador] = lambda: Importador(Resolvedor(g, reg, FakeAliases(), espanol={}), g)
    c = TestClient(app, headers={"Authorization": f"Bearer {TEST_TOKEN}"})
    hoja = "Fecha,Ingrediente activo,Dosis,Lote\n18-sep,Chlorpyrifos,0.25 L/cil,B2\n20-sep,Producto raro,1 L/ha,B2\n"
    body = {"crop": "table_grape", "markets": ["EU"], "harvest_on": "2026-12-28", "file_name": "p.csv",
            "file_base64": base64.b64encode(hoja.encode()).decode()}
    out = c.post("/api/programas/importar", json=body).json()
    assert fake_accounts.audits[-1][:2] == (ANA.id, "programa_importado")
    a, b = out["rows"]
    assert (a["status"], a["product_id"], a["applied_on"], a["dose"]["status"]) == (
        "resolved_by_ingredient", "LORSBAN", "2026-09-18", "within")
    assert b["status"] == "needs_review" and out["summary"]["necesitan_persona"] == 1
    assert out["program"]["blocks"] == [{"key": "B2", "harvest_on": "2026-12-28", "markets": ["EU"]}]
    assert out["program"]["applications"][0]["product_id"] == "LORSBAN"
    assert c.post("/api/programas/importar", json={**body, "file_base64": "%%%"}).status_code == 400
    assert c.post("/api/programas/importar", json={**body, "file_name": "p.pdf"}).status_code == 400
