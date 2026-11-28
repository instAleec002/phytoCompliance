"""Early alerts for limits not yet applicable."""
from datetime import date

from domain.alerts.upcoming import alerts_for, alerts_for_program
from domain.validation.models import Application, Block, Program

from .fakes import FakeLimits, FakeRegistry, mrl

TODAY = date(2026, 10, 28)


def limits():
    return FakeLimits().add("x", [mrl("X", 0.5, date(2015, 1, 1), date(2027, 3, 1)),
                                  mrl("X", 0.01, date(2027, 3, 1), regulation="Reg. (EU) 2026/900", annex="II"),
                                  mrl("X", 0.01, date(2027, 3, 1), regulation="Reg. (EU) 2026/900", annex="III")])


def test_alert_compares_today_with_the_new_limit():
    [a] = alerts_for(limits(), "x", "blueberry", "EU", TODAY)
    assert (a.current_mg_kg, a.new_mg_kg, a.applies_from, a.stricter) == (0.5, 0.01, date(2027, 3, 1), True)
    assert a.days_left(TODAY) == 124 and a.regulation == "Reg. (EU) 2026/900"


def test_horizon_filters_far_changes():
    assert alerts_for(limits(), "x", "blueberry", "EU", TODAY, horizon_days=90) == []
    assert len(alerts_for(limits(), "x", "blueberry", "EU", TODAY, horizon_days=200)) == 1


def test_no_alert_once_the_change_applies():
    assert alerts_for(limits(), "x", "blueberry", "EU", date(2027, 3, 1)) == []


def test_program_alert_marks_blocks_harvested_after_the_change():
    registry = FakeRegistry().add("P", ["x"], 7)
    prog = Program("blueberry", (Block("early", date(2027, 1, 15), ("EU",)), Block("late", date(2027, 4, 1), ("EU",))),
                   (Application("early", "P", date(2026, 12, 1)), Application("late", "P", date(2027, 2, 1))))
    [a] = alerts_for_program(prog, registry, limits(), TODAY)
    assert a.blocks_affected == ("late",)
