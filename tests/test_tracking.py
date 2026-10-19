import datetime

from ginot import tracking


def row(num, deadline=""):
    return {"pl_number": num,
            "objection_deadline_derived_60d_from_publication": deadline}


def test_defaults_to_new():
    rows, changed = tracking.merge([row("1")], {}, today=datetime.date(2026, 10, 20))
    assert changed and rows[0]["tracking_state"] == "new"


def test_advisory_urgent_window():
    states = {"1": {"state": "reviewed", "updated": "2026-10-01", "note": ""}}
    rows, _ = tracking.merge([row("1", "2026-11-05")], states, today=datetime.date(2026, 10, 20))
    assert rows[0]["tracking_state"] == "urgent" and rows[0]["tracking_urgent_advisory"]
    # decided states are not auto-urgent
    states["1"]["state"] = "objection_filed"
    rows, _ = tracking.merge([row("1", "2026-11-05")], states, today=datetime.date(2026, 10, 20))
    assert rows[0]["tracking_state"] == "objection_filed"
    # outside window
    states["1"]["state"] = "new"
    rows, _ = tracking.merge([row("1", "2027-05-05")], states, today=datetime.date(2026, 10, 20))
    assert rows[0]["tracking_state"] == "new"
    # past deadline is not urgent
    rows, _ = tracking.merge([row("1", "2026-10-01")], states, today=datetime.date(2026, 10, 20))
    assert rows[0]["tracking_state"] == "new"


def test_set_state_and_roundtrip(tmp_path):
    st = tracking.set_state({}, "1", "objection_filed", "הוגש ב-20.10")
    p = str(tmp_path / "s.json")
    tracking.save(st, p)
    assert tracking.load(p)["1"]["state"] == "objection_filed"
    assert tracking.load(str(tmp_path / "none.json")) == {}
