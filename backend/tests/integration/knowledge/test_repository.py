"""The domain ports over the graph: the same rules the unit tests check in memory, fed by AGE. Skipped when the
database is not running (make db)."""
from datetime import date

from domain.compliance.limits import limit_on
from domain.compliance.models import LimitStatus
from domain.validation.models import Application, Block, Program
from domain.validation.program import validate_program
from knowledge.graph.loader import rebuild
from knowledge.graph.repository import GraphRepository, NoModeOfActionData

from .test_graph_load import graph, records  # noqa: F401  (graph is a fixture)

TODAY = date(2026, 10, 28)


def repo(graph):  # noqa: F811
    rebuild(graph, records())
    return GraphRepository(graph)


def test_limit_through_the_repository(graph):  # noqa: F811
    r = repo(graph)
    assert r.loaded_markets() == {"EU"}
    lim = limit_on(r, "Pyraclostrobin", "blueberry", "EU", TODAY)
    assert (lim.status, lim.value_mg_kg, lim.regulation) == (LimitStatus.SPECIFIC, 4.0,
                                                              "Commission Regulation (EU) 2026/140")
    assert limit_on(r, "tolfenpyrad", "blueberry", "EU", TODAY).status is LimitStatus.DEFAULT


def test_registration_and_product(graph):  # noqa: F811
    r = repo(graph)
    reg = r.registration("P1", "blueberry", "000626")
    assert (reg.trade_name, reg.ingredients, reg.preharvest_interval_days) == ("ADIKO SC", ("pyraclostrobin",), 14)
    assert r.registration("P1", "blueberry", "999999") is None
    assert r.registration("P1", "blueberry").preharvest_interval_days == 14
    assert r.product("P1").ingredients == ("pyraclostrobin",)


def test_program_validated_over_the_graph(graph):  # noqa: F811
    r = repo(graph)
    prog = Program("blueberry", (Block("A", date(2026, 12, 1), ("EU",)),),
                   (Application("A", "P1", date(2026, 11, 25), "000626"),))
    report = validate_program(prog, r, r, NoModeOfActionData())
    assert report.codes() == ["PHI_NOT_MET", "ROTATION_NOT_CHECKED"]


def test_mode_of_action_from_the_graph(graph):  # noqa: F811
    from knowledge.graph.records import add_moa
    from knowledge.graph.repository import GraphModeOfAction
    from knowledge.normalization.moa import MoaIndex
    from knowledge.sources.moa.models import MoaEntry

    rec = records()
    add_moa(rec, MoaIndex([MoaEntry(scheme="FRAC", code="11", name="pyraclostrobin")]), "moa:test")
    rebuild(graph, rec)
    moa = GraphModeOfAction(graph)
    assert moa.groups("Pyraclostrobin") == {"FRAC:11"} and moa.groups("tolfenpyrad") == set()
    r = GraphRepository(graph)
    prog = Program("blueberry", (Block("A", date(2026, 12, 31), ("EU",)),),
                   (Application("A", "P1", date(2026, 11, 1), "000626"), Application("A", "P1", date(2026, 11, 10), "000626")))
    assert validate_program(prog, r, r, moa).codes() == ["ROTATION_SAME_GROUP"]
