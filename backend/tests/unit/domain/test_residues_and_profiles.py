"""Lab results against the MRL and the buyer profiles in config/buyer_profiles."""
from datetime import date
from pathlib import Path

import pytest

from domain.validation.profiles import BuyerProfile, load_profiles
from domain.validation.residues import LabResult, Measurement, check_lab_result

from .fakes import PYRACLOSTROBIN, FakeLimits, mrl

PROFILES = Path(__file__).resolve().parents[3] / "config" / "buyer_profiles"
DAY = date(2026, 10, 28)


@pytest.fixture
def lidl():
    return load_profiles(PROFILES)["lidl_2025"]


def limits():
    src = FakeLimits(markets={"EU", "US"}).add("pyraclostrobin", PYRACLOSTROBIN)
    for name, value in (("fludioxonil", 4.0), ("cyprodinil", 8.0), ("fenhexamid", 20.0), ("boscalid", 10.0),
                        ("captan", 30.0)):
        src.add(name, [mrl(name.title(), value, date(2020, 1, 1))])
    return src


def lot(*measurements, market="EU"):
    return LabResult("L-1", "blueberry", market, DAY, tuple(Measurement(i, v) for i, v in measurements))


def test_profiles_load_from_config(lidl):
    assert (lidl.max_fraction_of_mrl_per_substance, lidl.max_sum_of_mrl_fractions, lidl.max_number_of_residues) == \
           (0.333, 0.80, 5)


def test_unknown_criterion_is_rejected():
    with pytest.raises(ValueError):
        BuyerProfile.from_dict("x", {"max_fraction": 0.5})


def test_legal_check_only():
    found = check_lab_result(lot(("pyraclostrobin", 4.5), ("fludioxonil", 1.0)), limits())
    assert [(f.code, f.ingredient) for f in found] == [("MRL_EXCEEDED", "pyraclostrobin")]
    assert found[0].evidence["regulation"] == "Commission Regulation (EU) 2026/140"


def test_detected_residue_without_limit_breaks_the_default():
    [f] = check_lab_result(lot(("tolfenpyrad", 0.02)), limits())
    assert f.code == "MRL_EXCEEDED" and f.evidence["value_mg_kg"] == 0.01


def test_us_without_tolerance():
    [f] = check_lab_result(lot(("tolfenpyrad", 0.005), market="US"), limits())
    assert f.code == "RESIDUE_NOT_PERMITTED"


def test_lidl_fraction_per_substance(lidl):
    found = check_lab_result(lot(("pyraclostrobin", 1.6)), limits(), lidl)   # 40 % of 4 mg/kg: legal, not for Lidl
    assert [f.code for f in found] == ["PROFILE_SUBSTANCE", "PROFILE_ARFD_NOT_CHECKED"]


def test_lidl_sum_and_count(lidl):
    result = lot(("pyraclostrobin", 1.2), ("fludioxonil", 1.2), ("cyprodinil", 2.0), ("fenhexamid", 1.0),
                 ("boscalid", 1.0), ("captan", 1.0))                       # 0.30 + 0.30 + 0.25 + 0.05 + 0.10 + 0.03
    codes = [f.code for f in check_lab_result(result, limits(), lidl)]
    assert codes == ["PROFILE_SUM", "PROFILE_COUNT", "PROFILE_ARFD_NOT_CHECKED"]


def test_non_detects_do_not_count(lidl):
    result = lot(("pyraclostrobin", 0.1), *[(f"x{i}", 0.0) for i in range(8)])
    assert [f.code for f in check_lab_result(result, limits(), lidl)] == ["PROFILE_ARFD_NOT_CHECKED"]


def test_residue_without_value_cannot_be_compared():
    src = limits().add("fosetyl", [mrl("Fosetyl", None, date(2025, 4, 29), footnote="phosphonic acid applies")])
    [f] = check_lab_result(lot(("fosetyl", 0.3)), src)
    assert f.code == "LIMIT_WITHOUT_VALUE" and "phosphonic acid" in f.message
