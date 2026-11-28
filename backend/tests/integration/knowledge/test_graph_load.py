"""Rebuilds a small graph in the local AGE database and queries it. Skipped when the database is not running
(make db)."""
import json
from datetime import date

import psycopg
import pytest

from knowledge.graph import queries as Q
from knowledge.graph.age import AgeGraph
from knowledge.graph.loader import rebuild, verify
from knowledge.graph.records import GraphRecords, _add_mrl_versions
from knowledge.sources.eu_mrl.parser import parse_mrl
from shared.settings import settings

GRAPH = "fito_test"


@pytest.fixture(scope="module")
def graph():
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local database not running (make db)")
    conn.execute("LOAD 'age'")
    conn.execute('SET search_path = ag_catalog, "$user", public')
    if not conn.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s", (GRAPH,)).fetchone():
        conn.execute("SELECT create_graph(%s)", (GRAPH,))
    g = AgeGraph(conn, GRAPH)
    yield g
    conn.execute("SELECT drop_graph(%s, true)", (GRAPH,))
    conn.close()


def records() -> GraphRecords:
    rec = GraphRecords()
    rec.node("Crop", "blueberry", name_es="arándano")
    rec.node("Market", "EU", name="Unión Europea")
    rec.node("Ingredient", "pyraclostrobin")
    rec.node("Product", "P1", trade_name="ADIKO SC", product_type="QUIMICO")
    rec.node("Pest", "000626", scientific_name="Botrytis cinerea")
    rec.node("Authorization", "P1:blueberry:000626", preharvest_interval_days=14)
    rec.edge("OF_PRODUCT", "P1:blueberry:000626", "P1")
    rec.edge("ON_CROP", "P1:blueberry:000626", "blueberry")
    rec.edge("AGAINST", "P1:blueberry:000626", "000626")
    rec.edge("CONTAINS", "P1", "pyraclostrobin")
    rec.edge("MEASURED_AS", "pyraclostrobin", "EU:195")
    rows = [{"pesticide_residue_id": 195, "product_id": 46, "mrl_value": v, "applicability_text": s,
             "application_date": d, "regulation_number": r, "included_in_annex": "Annex II"}
            for v, s, d, r in [("0.5", "No longer applicable", "01/09/2008", "Reg A"),
                               ("4", "No longer applicable", "26/04/2017", "Reg. (EU) 2017/623"),
                               ("4", "Applicable", "11/02/2026", "Commission Regulation (EU) 2026/140")]]
    _add_mrl_versions(rec, [parse_mrl(r) for r in rows], "blueberry", {195: {"EN": "Pyraclostrobin (F)"}}, "eu_mrl:test")
    return rec


def test_rebuild_is_complete_and_repeatable(graph):
    rec = records()
    first = rebuild(graph, rec)
    assert verify(graph, rec) == {}
    assert rebuild(graph, rec) == first and verify(graph, rec) == {}  # same snapshots, same graph


def test_limit_in_force_on_a_date(graph):
    rebuild(graph, records())
    today = Q.mrl_on(graph, "pyraclostrobin", "blueberry", date(2026, 10, 28))
    assert [(m["value_mg_kg"], m["regulation"]) for m in today] == [(4, "Commission Regulation (EU) 2026/140")]
    then = Q.mrl_on(graph, "pyraclostrobin", "blueberry", date(2009, 1, 1))
    assert [m["value_mg_kg"] for m in then] == [0.5]


def test_authorized_products(graph):
    rebuild(graph, records())
    products = Q.authorized_products(graph, "blueberry", "000626")
    assert products == [{"trade_name": "ADIKO SC", "registration_number": None, "product_type": "QUIMICO",
                         "preharvest_interval_days": 14, "ingredients": ["pyraclostrobin"]}]
    assert json.dumps(products)  # plain JSON, ready for the API
