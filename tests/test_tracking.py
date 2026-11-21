import datetime

from ginot import tracking


def row(num, deadline=""):
    return {
        "pl_number": num,
        "objection_deadline_derived_2m_from_publication": deadline,
    }


def test_defaults_to_new():
    rows, changed = tracking.merge([row("1")], {}, today=datetime.date(2026, 10, 20))
    assert changed and rows[0]["tracking_state"] == "new"


def test_advisory_urgent_window():
    states = {"1": {"state": "reviewed", "updated": "2026-10-01", "note": ""}}
    rows, _ = tracking.merge(
        [row("1", "2026-11-05")], states, today=datetime.date(2026, 10, 20)
    )
    assert rows[0]["tracking_state"] == "urgent" and rows[0]["tracking_urgent_advisory"]
    # decided states are not auto-urgent
    states["1"]["state"] = "objection_filed"
    rows, _ = tracking.merge(
        [row("1", "2026-11-05")], states, today=datetime.date(2026, 10, 20)
    )
    assert rows[0]["tracking_state"] == "objection_filed"
    # outside window
    states["1"]["state"] = "new"
    rows, _ = tracking.merge(
        [row("1", "2027-05-05")], states, today=datetime.date(2026, 10, 20)
    )
    assert rows[0]["tracking_state"] == "new"
    # past deadline is not urgent
    rows, _ = tracking.merge(
        [row("1", "2026-10-01")], states, today=datetime.date(2026, 10, 20)
    )
    assert rows[0]["tracking_state"] == "new"


def test_set_state_and_roundtrip(tmp_path):
    st = tracking.set_state({}, "1", "objection_filed", "הוגש ב-20.10")
    p = str(tmp_path / "s.json")
    tracking.save(st, p)
    assert tracking.load(p)["1"]["state"] == "objection_filed"
    assert tracking.load(str(tmp_path / "none.json")) == {}


def test_advisory_urgent_prefers_verified_deadline():
    """The urgent advisory measures days-to-deadline from the verified
    deadline when present, not the derived 2m estimate (#1081 post-merge
    review P2: a one-day difference flips the advisory)."""
    states = {"1": {"state": "reviewed", "updated": "2026-10-01", "note": ""}}
    r = row("1", "2026-12-30")  # derived 2m: 39 days out, NOT urgent
    r["objection_deadline_verified"] = "2026-12-29"  # verified: 38 days out
    rows, _ = tracking.merge([r], states, today=datetime.date(2026, 11, 21))
    assert rows[0]["tracking_urgent_advisory"] is False  # both > 30 days
    rows, _ = tracking.merge(
        [dict(r)], {"1": dict(states["1"])}, today=datetime.date(2026, 11, 29)
    )
    # On 29.11: verified 29.12 is exactly 30 days out (urgent); the derived
    # 30.12 is 31 days out, so only verified-first flags the advisory.
    assert rows[0]["tracking_urgent_advisory"] is True
    # Same day, verified already past but derived still open: not urgent.
    r2 = row("2", "2026-12-01")
    r2["objection_deadline_verified"] = "2026-11-29"
    rows, _ = tracking.merge([r2], {}, today=datetime.date(2026, 11, 30))
    assert rows[0]["tracking_urgent_advisory"] is False
