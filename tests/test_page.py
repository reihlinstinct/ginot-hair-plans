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


def test_default_sort_deadline_desc():
    import datetime
    today = datetime.date.today()
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


def test_date_format_and_controls(tmp_path):
    rows = [_row("1", "הפקדה להתנגדויות", recv="2026-10-01", dep="2026-10-10",
                 deadline="2026-12-09"),
            _row("2", "אישור", recv="2019-05-02")]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # DD.MM.YYYY display with ISO preserved for sorting/filtering
    assert "01.10.26" in html and "data-iso='2026-10-01'" in html and "dir='ltr'" in html
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


def _permits(tmp_path):
    import json
    reqs = {"requests": [
        {"tik_num": "2026/0001.01", "address": "רחוב א 1", "mahut": "תוספת קומה",
         "sugbakasha": "היתר בניה", "status": "נפתח תיק רישוי",
         "status_date": "2026-09-01", "publication_start": "2026-10-01",
         "publication_end_planned": "2026-11-01", "gush": 30001, "helka": 5},
        {"tik_num": "2024/0002.02", "address": "רחוב ב 2", "mahut": "שימוש חורג",
         "sugbakasha": "רישוי עסקים - שימוש חורג מתוכנית", "status": "הבקשה נסגרה",
         "status_date": "", "publication_start": "", "publication_end_planned": "",
         "gush": 30002, "helka": 6},
    ]}
    pp = tmp_path / "permits.json"
    pp.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
    return str(pp)


def test_permits_filters_dates_default_active(tmp_path):
    from ginot import page
    rows = [_row("1", "הפקדה להתנגדויות", recv="2026-10-01", dep="2026-10-10",
                 deadline="2026-12-09")]
    page.render_site(rows, [], str(tmp_path), permits_path=_permits(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # dates render dd.mm.yy with ISO kept for filtering
    assert "01.10.26" in html and "data-iso='2026-10-01'" in html
    # active vs terminal flags: open file active, closed request terminal
    assert "data-active='1'" in html and "data-active='0'" in html
    # filter controls present, terminal hidden by default (checkbox unchecked)
    for cid in ("pfq", "pfstatus", "pfsug", "pffrom", "pfto", "pfclosed",
                "pfreset", "pfcount", "pmore"):
        assert f'id="{cid}"' in html
    assert "הצג בקשות שהסתיימו (1)" in html
    assert "מוסתרות כברירת מחדל" in html
    # search text carries number/address/essence/type/gush/helka
    assert "2026/0001.01" in html and "גוש 30001" in html and "חלקה 5" in html
    # municipality SPA note, no invented per-request deep link
    assert "ykpubdata.jerusalem.muni.il" in html
