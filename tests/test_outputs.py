from shapely.geometry import Polygon
from ginot import outputs

MS_DAY = 86400000
PUB = 1750000000000  # fixed epoch ms


def attrs(**kw):
    base = {"pl_number": "101-0001", "pl_name": "test", "station_desc": "הפקדה להתנגדויות/השגות",
            "receiving_date": PUB, "pl_date_advertise": PUB, "pl_area_dunam": 5.0,
            "pl_url": "https://mavat.iplan.gov.il/..."}
    base.update(kw)
    return base


def test_dates_and_derived_deadline():
    r = outputs.row_from_feature(attrs(), None, None)
    assert r["receiving_date"] == "2025-06-15"
    assert r["objection_deadline_derived_60d_from_publication"] == "2025-08-14"
    assert r["inside_flag"] == ""


def test_deadline_fallback_chain():
    r = outputs.row_from_feature(attrs(pl_date_advertise=None, pl_last_deposit_date=PUB), None, None)
    assert r["objection_deadline_derived_60d_from_publication"] == "2025-08-14"
    r = outputs.row_from_feature(attrs(pl_date_advertise=None, pl_last_deposit_date=None,
                                       depositing_date=PUB), None, None)
    assert r["objection_deadline_derived_60d_from_publication"] == "2025-08-14"
    r = outputs.row_from_feature(attrs(pl_date_advertise=None, pl_last_deposit_date=None,
                                       depositing_date=None), None, None)
    assert r["objection_deadline_derived_60d_from_publication"] == ""


def test_inside_partial_classification():
    council = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    inside = {"rings": [[[10, 10], [20, 10], [20, 20], [10, 20], [10, 10]]]}
    partial = {"rings": [[[90, 90], [200, 90], [200, 200], [90, 200], [90, 90]]]}
    assert outputs.row_from_feature(attrs(), inside, council)["inside_flag"] == "inside"
    assert outputs.row_from_feature(attrs(), partial, council)["inside_flag"] == "partial"


def test_sort_by_receiving_date():
    feats = [{"attributes": attrs(pl_number="b", receiving_date=PUB + MS_DAY)},
             {"attributes": attrs(pl_number="a", receiving_date=PUB)}]
    rows = outputs.rows_from_features(feats, None)
    assert [r["pl_number"] for r in rows] == ["a", "b"]
    outputs.write_csv(rows, "/tmp/t.csv")
    outputs.write_xlsx(rows, "/tmp/t.xlsx")
