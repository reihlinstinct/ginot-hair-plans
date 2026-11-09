from ginot import page

# Section: Dates fixtures


def _row(n, status, recv="", dep="", deadline="", flag="inside"):
    return {
        "pl_number": str(n),
        "pl_name": f"תכנית {n}",
        "station_desc": status,
        "receiving_date": recv,
        "pl_last_deposit_date": dep,
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": deadline,
        "pl_area_dunam": 1.0,
        "inside_flag": flag,
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }


def _urgent_ul(html):
    import re

    return re.search(r'<ul id="urgent-list">(.*?)</ul>', html, re.DOTALL).group(1)


# Section: Dates behavior


def test_default_sort_deadline_desc():
    import datetime

    from ginot.dates import today_il

    # sort_rows defaults to the Jerusalem clock; build the fixture on the same one.
    today = today_il()
    near = (today + datetime.timedelta(days=10)).isoformat()
    far = (today + datetime.timedelta(days=40)).isoformat()
    rows = [
        _row("no-deadline-new", "בבדיקה תכנונית", recv="2026-01-01"),
        _row("open-near", "הפקדה להתנגדויות", dep="2026-09-01", deadline=near),
        _row("no-deadline-old", "אישור", recv="2019-01-01"),
        _row("open-far", "הפקדה להתנגדויות", dep="2026-09-01", deadline=far),
    ]
    order = [r["pl_number"] for r in page.sort_rows(rows)]
    # farthest deadline first; no-deadline rows below, newest entry first
    assert order == ["open-far", "open-near", "no-deadline-new", "no-deadline-old"]


def test_urgent_window_server_fallback(tmp_path):
    import datetime

    from ginot.dates import today_il

    # Anchor to the site's clock, not the runner's: render_site anchors the
    # urgent window to today_il(), which leads UTC by a day from 21:00-24:00
    # UTC (summer) and broke this test on runners in that window (run
    # 40041184013, issue #388; same class as #331).
    t = today_il()

    def dl(days):
        return (t + datetime.timedelta(days=days)).isoformat()

    rows = [
        _row(1, "הפקדה", dep=dl(-55), deadline=dl(5)),
        _row(2, "הפקדה", dep=dl(-55), deadline=dl(30)),
        _row(3, "הפקדה", dep=dl(-55), deadline=dl(31)),
        _row(4, "הפקדה", dep=dl(-55), deadline=dl(-1)),
        _row(5, "בדיקה תכנונית"),
    ]
    page.render_site(rows, [], str(tmp_path))
    ul = _urgent_ul((tmp_path / "index.html").read_text(encoding="utf-8"))
    assert ">1</a>" in ul and ">2</a>" in ul  # 5 and 30 days: inside [0,30]
    assert ">3</a>" not in ul  # 31 days: outside
    assert ">4</a>" not in ul  # past deadline: outside
    assert ">5</a>" not in ul  # no deadline: outside
    assert ul.index(">1</a>") < ul.index(">2</a>")  # nearest deadline first


def test_urgent_window_anchors_to_jerusalem_date(tmp_path, monkeypatch):
    """Run 40041184013 (#388): the server fallback must window against
    today_il(); pin it with a fixed Jerusalem date so no wall clock is involved."""
    import datetime

    fixed = datetime.date(2026, 1, 1)
    monkeypatch.setattr(page, "today_il", lambda: fixed)

    def dl(days):
        return (fixed + datetime.timedelta(days=days)).isoformat()

    rows = [
        _row(1, "הפקדה", dep=dl(-55), deadline=dl(5)),
        _row(2, "הפקדה", dep=dl(-55), deadline=dl(30)),
        _row(3, "הפקדה", dep=dl(-55), deadline=dl(31)),
        _row(4, "הפקדה", dep=dl(-55), deadline=dl(-1)),
    ]
    page.render_site(rows, [], str(tmp_path))
    ul = _urgent_ul((tmp_path / "index.html").read_text(encoding="utf-8"))
    assert ">1</a>" in ul and ">2</a>" in ul
    assert ">3</a>" not in ul and ">4</a>" not in ul


def test_urgent_client_side_machinery(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'id="urgent-list"' in html
    assert "URGENT_DAYS=30" in html
    assert "Asia/Jerusalem" in html  # today resolved in the site's timezone
    assert "get('today')" in html  # ?today=YYYY-MM-DD test/QA hook


def test_today_hook_and_timezone(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Asia/Jerusalem" in html  # today resolved in the site's timezone
    assert "get('today')" in html  # ?today=YYYY-MM-DD test/QA hook


def test_today_il_helper_uses_jerusalem_not_utc(monkeypatch):
    """Issue #331: today_il() must read Asia/Jerusalem, not the runner's UTC clock."""
    import datetime as dt

    from ginot import dates

    class Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            base = dt.datetime(2026, 7, 1, 21, 30, 0, tzinfo=dt.timezone.utc)
            return base.astimezone(tz) if tz else base

    monkeypatch.setattr(dates.datetime, "datetime", Frozen)
    # 21:30 UTC is already 00:30 the next day in Israel (summer, UTC+3)
    assert dates.today_il() == dt.date(2026, 7, 2)


def test_sort_rows_deadline_equal_to_utc_today_is_not_open_in_israel(monkeypatch):
    """Issue #331 regression test: a deadline equal to the UTC date, but
    already one day in the past by the Israel clock, must not be flagged as
    an open objection window."""
    import datetime as dt

    from ginot import dates

    class Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            base = dt.datetime(2026, 7, 1, 21, 30, 0, tzinfo=dt.timezone.utc)
            return base.astimezone(tz) if tz else base

    monkeypatch.setattr(dates.datetime, "datetime", Frozen)
    utc_today = "2026-07-01"  # the runner's (wrong) date at this instant
    row = _row(
        "deadline-is-utc-today",
        "הפקדה להתנגדויות",
        dep="2026-05-01",
        deadline=utc_today,
    )
    out = page.sort_rows([row])
    assert out[0]["_open_obj"] is False
