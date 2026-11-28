"""Which limit applies on a given day, per market."""
from datetime import date

from domain.compliance.limits import EU_DEFAULT_RULE, limit_on, upcoming
from domain.compliance.models import LimitStatus

from .fakes import PYRACLOSTROBIN, FakeLimits, mrl

TODAY = date(2026, 10, 28)


def test_specific_limit_in_force_today_cites_the_current_regulation():
    lim = limit_on(FakeLimits().add("pyraclostrobin", PYRACLOSTROBIN), "pyraclostrobin", "blueberry", "EU", TODAY)
    assert (lim.status, lim.value_mg_kg) == (LimitStatus.SPECIFIC, 4.0)
    assert lim.regulation == "Commission Regulation (EU) 2026/140"   # not Reg. 2017/623, in force for 76 days
    assert lim.snapshot == "eu_mrl:2026-10-27" and not lim.ambiguous


def test_limit_on_a_past_day_and_on_the_change_day():
    src = FakeLimits().add("pyraclostrobin", PYRACLOSTROBIN)
    assert limit_on(src, "pyraclostrobin", "blueberry", "EU", date(2010, 1, 1)).value_mg_kg == 0.5
    assert limit_on(src, "pyraclostrobin", "blueberry", "EU", date(2017, 4, 25)).value_mg_kg == 0.5
    on_change = limit_on(src, "pyraclostrobin", "blueberry", "EU", date(2017, 4, 26))
    assert (on_change.value_mg_kg, on_change.regulation) == (4.0, "Reg. (EU) 2017/623")


def test_eu_default_when_no_limit_is_listed():
    lim = limit_on(FakeLimits(), "tolfenpyrad", "blueberry", "EU", TODAY)
    assert (lim.status, lim.value_mg_kg, lim.regulation) == (LimitStatus.DEFAULT, 0.01, EU_DEFAULT_RULE)
    assert lim.any_detectable_residue_breaches


def test_default_keeps_the_known_reason_of_absence():
    src = FakeLimits()
    src.info_by[("tolfenpyrad", "EU")] = src.ingredient("tolfenpyrad", "EU").__class__(
        "tolfenpyrad", (), absence_reason="No aprobado en la UE")
    assert limit_on(src, "tolfenpyrad", "blueberry", "EU", TODAY).note == "No aprobado en la UE"


def test_eu_default_when_every_version_has_ended():
    src = FakeLimits().add("x", [mrl("X", 0.2, date(2010, 1, 1), date(2020, 1, 1))])
    assert limit_on(src, "x", "blueberry", "EU", TODAY).status is LimitStatus.DEFAULT


def test_exempt_substance_annex_iv():
    src = FakeLimits().add("kaolin", [mrl("Kaolin", None, date(2008, 9, 1), no_mrl_required=True)])
    lim = limit_on(src, "kaolin", "blueberry", "EU", TODAY)
    assert (lim.status, lim.value_mg_kg) == (LimitStatus.EXEMPT, None)
    assert not lim.any_detectable_residue_breaches


def test_limit_at_the_limit_of_determination():
    src = FakeLimits().add("x", [mrl("X", 0.01, date(2015, 1, 1), at_limit_of_determination=True)])
    lim = limit_on(src, "x", "blueberry", "EU", TODAY)
    assert lim.status is LimitStatus.SPECIFIC and lim.any_detectable_residue_breaches


def test_several_residues_use_the_strictest_and_say_so():
    oils = [mrl(f"Paraffin oil (CAS {n})", v, date(2015, 1, 1)) for n, v in (("64742-46-7", 0.01), ("8042-47-5", 0.5))]
    lim = limit_on(FakeLimits().add("mineral oil", oils), "mineral oil", "blueberry", "EU", TODAY)
    assert lim.value_mg_kg == 0.01 and lim.ambiguous and lim.residue == "Paraffin oil (CAS 64742-46-7)"


def test_version_with_unknown_end_is_not_used():
    src = FakeLimits().add("x", [mrl("X", 2.0, date(2012, 1, 1), end_date_unknown=True)])
    assert limit_on(src, "x", "blueberry", "EU", TODAY).status is LimitStatus.DEFAULT


def test_us_without_tolerance_is_not_permitted_and_codex_has_no_reference():
    src = FakeLimits(markets={"EU", "US", "CODEX"})
    assert limit_on(src, "x", "blueberry", "US", TODAY).status is LimitStatus.NOT_PERMITTED
    assert limit_on(src, "x", "blueberry", "CODEX", TODAY).status is LimitStatus.NO_REFERENCE


def test_market_not_loaded_answers_no_data_never_a_guess():
    lim = limit_on(FakeLimits(), "pyraclostrobin", "blueberry", "US", TODAY)
    assert (lim.status, lim.value_mg_kg) == (LimitStatus.NO_DATA, None)


def test_upcoming_versions_after_the_day_in_order():
    later = [mrl("X", 0.05, date(2027, 6, 1)), mrl("X", 0.5, date(2020, 1, 1)), mrl("X", 0.01, date(2027, 3, 1))]
    got = upcoming(FakeLimits().add("x", later), "x", "blueberry", "EU", TODAY)
    assert [v.applies_from for v in got] == [date(2027, 3, 1), date(2027, 6, 1)]


def test_listed_without_value_keeps_the_footnote():
    note = "The MRL for phosphonic acid applies and the default value of 0.01 mg/kg ... does not apply"
    src = FakeLimits().add("fosetyl", [mrl("Fosetyl", None, date(2025, 4, 29), footnote=note)])
    lim = limit_on(src, "fosetyl", "blueberry", "EU", TODAY)
    assert (lim.status, lim.value_mg_kg, lim.note) == (LimitStatus.WITHOUT_VALUE, None, note)
    assert not lim.any_detectable_residue_breaches


def test_residue_listed_without_any_row_for_the_crop_says_so():
    src = FakeLimits()
    src.info_by[("chitosan", "EU")] = src.ingredient("chitosan", "EU").__class__("chitosan", ("Chitosan",))
    lim = limit_on(src, "chitosan", "blueberry", "EU", TODAY)
    assert lim.status is LimitStatus.DEFAULT and "sin límite para este cultivo" in lim.note


def test_before_the_known_date_of_a_market_there_is_no_answer():
    src = FakeLimits(markets={"EU", "US"}, known={"US": date(2026, 10, 26)})
    src.add("pyraclostrobin", [mrl("Pyraclostrobin", 4.0, date(2026, 10, 26), history_known=False)], market="US")
    assert limit_on(src, "pyraclostrobin", "blueberry", "US", TODAY).value_mg_kg == 4.0
    before = limit_on(src, "pyraclostrobin", "blueberry", "US", date(2025, 1, 1))
    assert before.status is LimitStatus.NO_DATA and "26/10/2026" in before.note


def test_exemption_note_carries_the_conditions():
    src = FakeLimits().add("copper", [mrl("Copper", None, date(2020, 1, 1), no_mrl_required=True,
                                          footnote="exento como fungicida en cultivos en crecimiento")])
    assert "fungicida" in limit_on(src, "copper", "blueberry", "EU", TODAY).note
