import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "mirror_ingest",
    pathlib.Path(__file__).parent.parent / "scripts" / "mirror_ingest.py")
mirror_ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror_ingest)


def test_parcel_interval():
    assert mirror_ingest.parcel_interval({"מחלקה": "126", "עד חלקה": "126"}) == (set(), (126, 126))
    assert mirror_ingest.parcel_interval({"מחלקה": "49", "עד חלקה": "50"}) == (set(), (49, 50))


def test_parcel_interval_garbage_range_degrades_to_points():
    assert mirror_ingest.parcel_interval({"מחלקה": "216", "עד חלקה": "2"}) == ({216, 2}, None)
    assert mirror_ingest.parcel_interval({"מחלקה": "", "עד חלקה": ""}) == (set(), None)


def test_huge_common_property_range_matches_by_interval():
    parcels = {30002: {4000, 6000}}
    row = {"גוש": "30002", "מחלקה": "22", "עד חלקה": "5032"}
    _, hits = mirror_ingest.matching_parcels(row, parcels)
    assert hits == [4000]


def test_matching_parcels_intersects_council_set():
    parcels = {30025: {126, 127, 130}}
    row = {"גוש": "30025", "מחלקה": "125", "עד חלקה": "128"}
    gush, hits = mirror_ingest.matching_parcels(row, parcels)
    assert gush == 30025 and hits == [126, 127]
    row = {"גוש": "30025", "מחלקה": "1", "עד חלקה": "2"}
    _, hits = mirror_ingest.matching_parcels(row, parcels)
    assert hits == []


def test_map_record_drops_personal_and_shapes_fields():
    row = {"מספר תיק": "2026/0001.00", "סטטוס": "נפתח תיק רישוי",
           "תאריך סטטוס": "2026-10-01T00:00:00", "סוג בקשה": "בניה חדשה",
           "מהות הבקשה": " בניין  ", "רחוב": "י. אלפסי", "מספר בית": "9",
           "שכונה": "גינות העיר", "תאריך דגימה": "2026-10-17T21:55:48Z",
           "first_seen": "2026-10-17T21:55:58+00:00", "last_seen": None,
           "בעלי עניין": "שם פרטי (בעל הנכס)"}
    rec = mirror_ingest.map_record(row, 30025, [126])
    assert rec["tik_num"] == "2026/0001.00"
    assert rec["status_date"] == "2026-10-01"
    assert rec["address"] == "י. אלפסי 9 גינות העיר"
    assert rec["mahut"] == "בניין"
    assert "שם פרטי" not in str(rec) and "בעלי עניין" not in rec
