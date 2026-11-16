"""Regression: statutory objection window is 2 calendar MONTHS, not 60 days.

Planning and Building Law 5725-1965 s.102 sets the objection window for
deposited plans at two months from the latest newspaper publication of the
deposit notice. Length and end date follow Interpretation Law 5741-1981
s.10(b): the period ends on the same day-of-month in the final month, or the
final month's last day when short (31.12 + 2m -> 28/29.02).

Rest-day postponement (s.10(c)) is deliberately NOT applied to the derived
field: the true final day can then only be LATER than the derived date, so
the derived date stays on the safe (earlier) side for filers. The legacy
+60d field is kept untouched for API compatibility.
"""

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ginot import outputs, refresh


def _ms(iso: str) -> int:
    return int(
        datetime.datetime.fromisoformat(iso)
        .replace(tzinfo=datetime.timezone.utc)
        .timestamp()
        * 1000
    )


# Section: plus_months calendar rules (Interpretation Law s.10(b))


def test_plus_months_same_day_of_month():
    assert outputs.plus_months("2026-09-19", 2) == "2026-11-19"
    assert outputs.plus_months("2026-08-31", 2) == "2026-10-31"
    assert outputs.plus_months("2026-10-15", 2) == "2026-12-15"


def test_plus_months_year_boundary():
    assert outputs.plus_months("2026-12-10", 2) == "2027-02-10"


def test_plus_months_short_final_month_ends_on_its_last_day():
    assert outputs.plus_months("2025-12-31", 2) == "2026-02-28"
    assert outputs.plus_months("2027-12-31", 2) == "2028-02-29"  # leap year


def test_plus_months_empty_publication_stays_empty():
    assert outputs.plus_months("", 2) == ""


# Section: rest-day (Saturday) end is NOT postponed (documented safe side)


def test_saturday_end_is_not_postponed():
    # 2026-11-14 is a Saturday. s.10(c) would move the true final day later;
    # the derived field keeps the Saturday so it never exceeds the true date.
    assert outputs.plus_months("2026-09-14", 2) == "2026-11-14"


# Section: row_from_feature derives both fields from the publication date


def test_row_derives_60d_and_2m_from_publication():
    # HaPalmach 49 (101-1377753): newspaper publication 19.09.2026. Legacy
    # +60d shows 18.11.2026; the statutory s.102 window ends 19.11.2026.
    row = outputs.row_from_feature(
        {"pl_number": "101-1377753", "pl_date_advertise": _ms("2026-09-19")},
        None,
        None,
    )
    assert row["objection_deadline_derived_60d_from_publication"] == "2026-11-18"
    assert row["objection_deadline_derived_2m_from_publication"] == "2026-11-19"


def test_row_without_publication_derives_nothing():
    row = outputs.row_from_feature({"pl_number": "X"}, None, None)
    assert row["objection_deadline_derived_60d_from_publication"] == ""
    assert row["objection_deadline_derived_2m_from_publication"] == ""


# Section: 60d is NOT always the conservative side (pins the documented caveat)


def test_60d_can_land_after_the_statutory_2m_window():
    # Publication 15.01.2027 (non-leap year): +60d is 16.03, +2 months is the
    # statutory 15.03 - the 60d field is one day LATER, so it must not be
    # described as the conservative basis for these publication dates.
    row = outputs.row_from_feature(
        {"pl_number": "T", "pl_date_advertise": _ms("2027-01-15")}, None, None
    )
    assert row["objection_deadline_derived_60d_from_publication"] == "2027-03-16"
    assert row["objection_deadline_derived_2m_from_publication"] == "2027-03-15"
    # 31.12.2026 publication: +60d 01.03.2027 vs statutory 28.02.2027.
    row = outputs.row_from_feature(
        {"pl_number": "T", "pl_date_advertise": _ms("2026-12-31")}, None, None
    )
    assert row["objection_deadline_derived_60d_from_publication"] == "2027-03-01"
    assert row["objection_deadline_derived_2m_from_publication"] == "2027-02-28"


# Section: merge_land_status recomputes both fields from the latest publication


def test_merge_land_status_sets_2m_from_latest_publication(tmp_path):
    land = tmp_path / "land.json"
    land.write_text(
        json.dumps(
            {
                "plans": {
                    "P1": {
                        "land_status": "הפקדה",
                        "land_status_date": "2026-11-10",
                        "land_plan_id": 7,
                        "is_deposit_publication": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "pl_number": "P1",
            "pl_date_advertise": "2026-10-01",
            "objection_deadline_derived_60d_from_publication": "2026-11-30",
            "objection_deadline_derived_2m_from_publication": "2026-12-01",
        }
    ]
    out = refresh.merge_land_status(rows, str(land))
    # Latest publication is the land date 2026-11-10: +60d and +2 months.
    assert out[0]["objection_deadline_derived_60d_from_publication"] == "2027-01-09"
    assert out[0]["objection_deadline_derived_2m_from_publication"] == "2027-01-10"
    assert "publication" in out[0]["deadline_source_note"]
