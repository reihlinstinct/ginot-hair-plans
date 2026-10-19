from ginot import page


def test_render_site(tmp_path):
    rows = [{"pl_number": "1", "pl_name": "תכנית א", "station_desc": "הפקדה להתנגדויות/השגות",
             "receiving_date": "2026-10-01", "pl_last_deposit_date": "2026-10-10",
             "depositing_date": "", "objection_deadline_derived_60d_from_publication": "2026-12-09",
             "pl_area_dunam": 3.2, "inside_flag": "inside", "mavat_url": "https://mavat.iplan.gov.il/x"}]
    changes = [{"kind": "new", "pl_number": "1", "pl_name": "תכנית א",
                "station_desc": "הפקדה", "mavat_url": "https://mavat.iplan.gov.il/x"}]
    rows[0]["advisory_urgent"] = True
    page.render_site(rows, changes, str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "אחרון להתנגדות" in html and "דחוף להתנגדות" in html
    assert "מעקב" not in html  # planner tracking column must not be public
    assert "class='new'" in html
    feed = (tmp_path / "feed.xml").read_text(encoding="utf-8")
    assert "<feed" in feed and "urn:ginot:1" in feed


def _row(n, status, recv="", dep="", deadline="", flag="inside"):
    return {"pl_number": str(n), "pl_name": f"תכנית {n}", "station_desc": status,
            "receiving_date": recv, "pl_last_deposit_date": dep, "depositing_date": "",
            "objection_deadline_derived_60d_from_publication": deadline,
            "pl_area_dunam": 1.0, "inside_flag": flag,
            "mavat_url": "https://mavat.iplan.gov.il/x"}


def test_relevance_ranking():
    import datetime
    today = datetime.date.today()
    near = (today + datetime.timedelta(days=10)).isoformat()
    far = (today + datetime.timedelta(days=40)).isoformat()
    rows = [
        _row("approved", "אישור", recv="2020-01-01"),
        _row("active-partial", "בבדיקה תכנונית", recv="2026-01-01", flag="partial"),
        _row("active-inside", "בבדיקה תכנונית", recv="2025-01-01"),
        _row("open-far", "הפקדה להתנגדויות", dep="2026-09-01", deadline=far),
        _row("open-near", "הפקדה להתנגדויות", dep="2026-09-01", deadline=near, flag="partial"),
    ]
    order = [r["pl_number"] for r in page.rank_rows(rows)]
    # open windows first by nearest deadline (flag does not trump deadline),
    # then active newest-first with inside before partial, approved last
    assert order == ["open-near", "open-far", "active-inside", "active-partial", "approved"]


def test_date_format_and_controls(tmp_path):
    rows = [_row("1", "הפקדה להתנגדויות", recv="2026-10-01", dep="2026-10-10",
                 deadline="2026-12-09"),
            _row("2", "אישור", recv="2019-05-02")]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # DD.MM.YYYY display with ISO preserved for sorting/filtering
    assert "01.10.2026" in html and "data-iso='2026-10-01'" in html
    # approved hidden by default, count stated, one-click control present
    assert "data-active='0'" in html and "הצג תכניות מאושרות (1)" in html
    assert "מוסתרות כברירת מחדל" in html
    # all filter controls + show-more present
    for cid in ("fq", "fstatus", "fflag", "fobj", "fappr", "ffrom", "fto", "freset", "more"):
        assert f'id="{cid}"' in html
    # table comes before statistics
    assert html.find("<table") < html.find("סטטיסטיקה")


def test_status_chips_and_legend(tmp_path):
    rows = [_row("1", "הפקדה להתנגדויות"), _row("2", "אישור"), _row("3", "בבדיקה תכנונית")]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'class="chip c-deposit"' in html and 'class="chip c-approved"' in html
    assert 'class="chip c-review"' in html
    assert "מקרא סטטוסים" in html and html.find("legend") < html.find("<table")
