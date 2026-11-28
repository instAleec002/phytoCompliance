"""Pre-harvest interval and mode-of-action rotation."""
from datetime import date

from domain.findings import Severity
from domain.harvest.preharvest import check, safe_harvest
from domain.rotation.sequence import check_rotation
from domain.validation.models import Application

from .fakes import FakeModeOfAction, FakeRegistry


def registry():
    return (FakeRegistry()
            .add("P1", ["pyraclostrobin", "boscalid"], 14)
            .add("P2", ["fludioxonil", "cyprodinil"], 7)
            .add("P3", ["fenhexamid"], None)
            .add("P4", ["captan"], 1)
            .add("P5", ["bacillus subtilis"], None, biological=True))


def test_safe_from_is_application_plus_interval():
    c = check(Application("A", "P1", date(2026, 11, 1), "000626"), "blueberry", registry())
    assert (c.interval_days, c.safe_from) == (14, date(2026, 11, 15))
    assert c.met_on(date(2026, 11, 15)) and not c.met_on(date(2026, 11, 14))


def test_safe_harvest_takes_the_latest_application_window():
    apps = [Application("A", "P1", date(2026, 11, 1), "000626"), Application("A", "P2", date(2026, 11, 12), "000626"),
            Application("B", "P1", date(2026, 12, 1), "000626")]
    got = safe_harvest("A", "blueberry", apps, registry())
    assert (got.safe_from, got.limiting.product_id, got.determined) == (date(2026, 11, 19), "P2", True)


def test_unknown_interval_leaves_the_date_undetermined():
    apps = [Application("A", "P1", date(2026, 11, 1), "000626"), Application("A", "P3", date(2026, 11, 2), "000626")]
    got = safe_harvest("A", "blueberry", apps, registry())
    assert got.safe_from == date(2026, 11, 15) and not got.determined
    assert [a.product_id for a in got.unknown] == ["P3"]


def test_unregistered_product_has_no_interval():
    c = check(Application("A", "P1", date(2026, 11, 1), "999999"), "blueberry", registry())
    assert c.safe_from is None and c.met_on(date(2027, 1, 1)) is None


MOA = FakeModeOfAction({"pyraclostrobin": {"FRAC:11"}, "boscalid": {"FRAC:7"}, "fludioxonil": {"FRAC:12"},
                        "cyprodinil": {"FRAC:9"}, "fenhexamid": {"FRAC:17"}, "captan": {"FRAC:M04"}})


def test_consecutive_same_group_is_a_risk():
    apps = [Application("A", "P1", date(2026, 11, 1)), Application("A", "P1", date(2026, 11, 10))]
    found = check_rotation("A", apps, registry(), MOA)
    assert {(f.code, f.evidence["group"]) for f in found} == {("ROTATION_SAME_GROUP", "FRAC:11"),
                                                             ("ROTATION_SAME_GROUP", "FRAC:7")}
    assert all(f.severity is Severity.RISK for f in found)


def test_alternating_groups_and_multisite_pass():
    apps = [Application("A", "P1", date(2026, 11, 1)), Application("A", "P2", date(2026, 11, 8)),
            Application("A", "P4", date(2026, 11, 15)), Application("A", "P4", date(2026, 11, 20)),
            Application("A", "P1", date(2026, 11, 25))]
    assert check_rotation("A", apps, registry(), MOA) == []


def test_order_is_by_date_and_per_block():
    apps = [Application("A", "P1", date(2026, 11, 20)), Application("B", "P1", date(2026, 11, 10)),
            Application("A", "P2", date(2026, 11, 10))]
    assert check_rotation("A", apps, registry(), MOA) == []


def test_missing_groups_are_reported_not_passed():
    found = check_rotation("A", [Application("A", "P3", date(2026, 11, 1)), Application("A", "P5", date(2026, 11, 5))],
                           registry(), FakeModeOfAction())
    assert [(f.code, f.evidence["ingredients"]) for f in found] == [("ROTATION_NOT_CHECKED", ["fenhexamid"])]


def test_interval_not_applicable_lets_the_harvest_follow():
    reg = FakeRegistry().add("BIO", ["bacillus subtilis"], None, biological=True, phi_not_applicable=True)
    c = check(Application("A", "BIO", date(2026, 11, 30), "000626"), "blueberry", reg)
    assert (c.not_applicable, c.safe_from, c.met_on(date(2026, 11, 30))) == (True, date(2026, 11, 30), True)
    assert safe_harvest("A", "blueberry", [c.application], reg).determined


def test_groups_are_compared_within_one_scheme_and_unspecific_ones_skipped():
    reg = FakeRegistry().add("S", ["sulphur"], 1).add("T", ["tolfenpyrad"], 7)
    moa = FakeModeOfAction({"sulphur": {"FRAC:M02", "IRAC:UN"}, "tolfenpyrad": {"FRAC:39", "IRAC:21A"}})
    apps = [Application("A", "S", date(2026, 11, 1)), Application("A", "S", date(2026, 11, 5)),
            Application("A", "T", date(2026, 11, 10)), Application("A", "T", date(2026, 11, 15))]
    found = check_rotation("A", apps, reg, moa)
    assert sorted(f.evidence["group"] for f in found) == ["FRAC:39", "IRAC:21A"]


def test_specific_groups():
    from domain.rotation.sequence import specific
    assert specific("FRAC:11") and specific("FRAC:P07") and specific("IRAC:4A") and specific("HRAC:9")
    assert not specific("FRAC:M02") and not specific("FRAC:BM02") and not specific("FRAC:U12")
    assert not specific("IRAC:UNF") and not specific("HRAC:0")
