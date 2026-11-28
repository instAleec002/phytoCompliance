"""Acute intake (IESTI, EFSA PRIMo 3.1) and the ARfD criterion of a buyer profile. Consumption figures from PRIMo 3.1
(children: blueberries NL child, table grapes FI child 3 years; adults: blueberries DE women 14-50)."""
from datetime import date
from pathlib import Path

import pytest

from domain.exposure.acute import UnknownCase, acute_intakes, iesti
from domain.ports import AcuteIntakeData, Arfd
from domain.validation.profiles import load_profiles
from domain.validation.residues import LabResult, Measurement, check_lab_result

from .fakes import FakeLimits, mrl

BLUEBERRY_CHILD = AcuteIntakeData("Blueberries", "children", "NL child", 5.962, 18.4, 109.7008, None, "1", 1)
BLUEBERRY_ADULT = AcuteIntakeData("Blueberries", "adults", "DE women 14-50", 9.118, 67.47, 615.19146, None, "1", 1)
GRAPE_CHILD = AcuteIntakeData("Table grapes", "children", "FI child 3 years", 14.58333372, 15.2, 221.666672544,
                              554.3666666666667, "2b", 5)
AVOCADO_ADULT = AcuteIntakeData("Avocados", "adults", "FI men", 4.0746054519, 84.7, 345.11908177593,
                                154.46571428571428, "2a", 7)


def test_case_1_is_large_portion_times_residue():
    assert iesti(1.0, BLUEBERRY_CHILD) == pytest.approx(0.005962)


def test_case_2b_applies_the_variability_factor_to_the_whole_portion():
    assert iesti(1.0, GRAPE_CHILD) == pytest.approx(0.221666672544 * 5 / 15.2)


def test_case_2a_applies_it_to_one_unit_only():
    u, lp = 0.15446571428571428, 0.34511908177593
    assert iesti(1.0, AVOCADO_ADULT) == pytest.approx((u * 7 + (lp - u)) / 84.7)


def test_unknown_case_fails_loudly():
    with pytest.raises(UnknownCase):
        iesti(1.0, AcuteIntakeData("X", "children", "d", 1, 10, 100, 50, "3", 1))


def test_most_critical_population_first():
    [first, second] = acute_intakes(1.0, 0.03, [BLUEBERRY_CHILD, BLUEBERRY_ADULT])
    assert (first.population, round(first.percent_of_arfd, 1)) == ("adults", 30.4)
    assert round(second.percent_of_arfd, 1) == 19.9


class FakeToxicology:
    def __init__(self, arfds, consumption):
        self.arfds, self.consumption = arfds, consumption

    def arfd(self, ingredient):
        return self.arfds.get(ingredient)

    def acute_consumption(self, crop):
        return self.consumption.get(crop, [])


@pytest.fixture
def lidl():
    return load_profiles(Path(__file__).resolve().parents[3] / "config" / "buyer_profiles")["lidl_2025"]


def grape_lot(*measurements):
    return LabResult("L-1", "table_grape", "EU", date(2026, 10, 28), tuple(Measurement(i, v) for i, v in measurements))


def limits():
    src = FakeLimits()
    for name in ("pyraclostrobin", "fludioxonil", "x"):
        src.add(name, [mrl(name, 50.0, date(2020, 1, 1))], crop="table_grape")
    return src


def test_profile_arfd_breach(lidl):
    tox = FakeToxicology({"pyraclostrobin": Arfd(0.03, "set", "Reg. (EU) 2026/1976")}, {"table_grape": [GRAPE_CHILD]})
    [f] = [f for f in check_lab_result(grape_lot(("pyraclostrobin", 1.0)), limits(), lidl, tox) if "ARFD" in f.code]
    assert f.code == "PROFILE_ARFD" and f.evidence["percent_of_arfd"] == 243.1 and f.evidence["diet"] == "FI child 3 years"


def test_profile_arfd_not_needed_or_missing(lidl):
    tox = FakeToxicology({"fludioxonil": Arfd(None, "not_needed")}, {"table_grape": [GRAPE_CHILD]})
    found = [f for f in check_lab_result(grape_lot(("fludioxonil", 1.0), ("x", 0.1)), limits(), lidl, tox)
             if "ARFD" in f.code]
    assert [(f.code, f.evidence.get("ingredients")) for f in found] == [("PROFILE_ARFD_NOT_CHECKED", ["x"])]


def test_profile_arfd_without_consumption_data(lidl):
    found = [f for f in check_lab_result(grape_lot(("x", 0.1)), limits(), lidl, FakeToxicology({}, {}))
             if "ARFD" in f.code]
    assert [f.code for f in found] == ["PROFILE_ARFD_NOT_CHECKED"] and "consumo" in found[0].message


def test_assessment_of_each_measurement():
    from domain.validation.residues import assess_measurements

    tox = FakeToxicology({"pyraclostrobin": Arfd(0.03, "set", "Reg. (EU) 2026/1976")}, {"table_grape": [GRAPE_CHILD]})
    rows = assess_measurements(grape_lot(("pyraclostrobin", 1.0), ("tolfenpyrad", 0.005)), limits(), tox)
    pyr, tolf = rows
    assert (pyr.fraction_of_mrl, round(pyr.acute.percent_of_arfd, 1)) == (0.02, 243.1)
    assert (tolf.limit.status.value, tolf.fraction_of_mrl, tolf.arfd_status, tolf.acute) == ("default", 0.5, "not_set", None)
