"""Validator of a program by block and market."""
from datetime import date

from domain.findings import Severity
from domain.validation.models import Application, Block, Program
from domain.validation.program import validate_program

from .fakes import PYRACLOSTROBIN, FakeLimits, FakeModeOfAction, FakeRegistry, mrl


def sources():
    registry = (FakeRegistry()
                .add("ADIKO", ["pyraclostrobin"], 14, name="ADIKO SC")
                .add("TOLF", ["tolfenpyrad"], 7, pest="000100", name="HACHI-HACHI")
                .add("BIO", ["bacillus subtilis"], 0, name="SERENADE", biological=True)
                .add("NOPHI", ["pyraclostrobin"], None, name="SIN CARENCIA"))
    limits = FakeLimits(markets={"EU", "US"}).add("pyraclostrobin", PYRACLOSTROBIN)
    limits.add("pyraclostrobin", [mrl("Pyraclostrobin", 4.0, date(2010, 1, 1))], market="US")
    return registry, limits, FakeModeOfAction({"pyraclostrobin": {"FRAC:11"}})


def program(*apps, markets=("EU",), harvest=date(2026, 12, 1)):
    return Program("blueberry", (Block("A", harvest, markets),), tuple(apps))


def test_compliant_program_has_no_findings():
    report = validate_program(program(Application("A", "ADIKO", date(2026, 11, 1), "000626")), *sources())
    assert report.findings == [] and report.verdict is None


def test_not_registered_for_the_pest_is_blocking_and_stops_further_checks():
    report = validate_program(program(Application("A", "ADIKO", date(2026, 11, 1), "000100")), *sources())
    assert report.codes() == ["NOT_REGISTERED"] and report.verdict is Severity.BLOCKING
    assert "ADIKO SC" in report.findings[0].message


def test_interval_not_met_says_until_when():
    report = validate_program(program(Application("A", "ADIKO", date(2026, 11, 20), "000626")), *sources())
    [f] = report.findings
    assert f.code == "PHI_NOT_MET" and f.evidence["safe_from"] == "2026-12-04" and "04/12/2026" in f.message


def test_unknown_interval_is_a_risk():
    report = validate_program(program(Application("A", "NOPHI", date(2026, 11, 1), "000626")), *sources())
    assert report.codes() == ["PHI_UNKNOWN"] and report.verdict is Severity.RISK


def test_default_limit_per_market():
    report = validate_program(program(Application("A", "TOLF", date(2026, 11, 1), "000100"), markets=("EU", "US")),
                              *sources())
    assert [(f.code, f.market) for f in report.findings] == [("DEFAULT_LIMIT", "EU"), ("NOT_PERMITTED", "US"),
                                                             ("ROTATION_NOT_CHECKED", None)]   # no group for it
    assert report.findings[0].evidence["value_mg_kg"] == 0.01


def test_biological_without_limit_is_only_information():
    report = validate_program(program(Application("A", "BIO", date(2026, 11, 30), "000626")), *sources())
    assert [(f.code, f.severity) for f in report.findings] == [("DEFAULT_LIMIT", Severity.INFO)]


def test_market_not_loaded_is_reported():
    report = validate_program(program(Application("A", "ADIKO", date(2026, 11, 1), "000626"), markets=("CODEX",)),
                              *sources())
    assert report.codes() == ["MARKET_NOT_LOADED"]


def test_unknown_block_and_application_after_harvest():
    report = validate_program(program(Application("Z", "ADIKO", date(2026, 11, 1), "000626"),
                                      Application("A", "ADIKO", date(2026, 12, 5), "000626")), *sources())
    assert set(report.codes()) == {"UNKNOWN_BLOCK", "APPLIED_AFTER_HARVEST", "PHI_NOT_MET"}


def test_rotation_findings_are_included_per_block():
    report = validate_program(program(Application("A", "ADIKO", date(2026, 10, 1), "000626"),
                                      Application("A", "ADIKO", date(2026, 10, 15), "000626")), *sources())
    assert report.codes() == ["ROTATION_SAME_GROUP"]
    assert list(report.by_block()) == ["A"]


def test_interval_not_applicable_is_not_reported_as_unknown():
    registry, limits, moa = sources()
    registry.add("BIO2", ["bacillus subtilis"], None, name="BIO NA", biological=True, phi_not_applicable=True)
    report = validate_program(program(Application("A", "BIO2", date(2026, 11, 30), "000626")), registry, limits, moa)
    assert "PHI_UNKNOWN" not in report.codes()
