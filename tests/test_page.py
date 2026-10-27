from ginot import page


def test_render_site(tmp_path):
    rows = [
        {
            "pl_number": "1",
            "pl_name": "תכנית א",
            "station_desc": "הפקדה להתנגדויות/השגות",
            "receiving_date": "2026-10-01",
            "pl_last_deposit_date": "2026-10-10",
            "depositing_date": "",
            "objection_deadline_derived_60d_from_publication": "2026-12-09",
            "pl_area_dunam": 3.2,
            "inside_flag": "inside",
            "mavat_url": "https://mavat.iplan.gov.il/x",
        }
    ]
    changes = [
        {
            "kind": "new",
            "pl_number": "1",
            "pl_name": "תכנית א",
            "station_desc": "הפקדה",
            "mavat_url": "https://mavat.iplan.gov.il/x",
        }
    ]
    rows[0]["advisory_urgent"] = True
    page.render_site(rows, changes, str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "אחרון להתנגדות" in html and "דחוף להתנגדות" in html
    assert "מעקב" not in html  # planner tracking column must not be public
    assert "class='new'" in html
    feed = (tmp_path / "feed.xml").read_text(encoding="utf-8")
    assert "<feed" in feed and "urn:ginot:1" in feed


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


def test_date_format_and_controls(tmp_path):
    rows = [
        _row(
            "1",
            "הפקדה להתנגדויות",
            recv="2026-10-01",
            dep="2026-10-10",
            deadline="2026-12-09",
        ),
        _row("2", "אישור", recv="2019-05-02"),
    ]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # DD.MM.YYYY display with ISO preserved for sorting/filtering
    assert (
        "01.10.26" in html and "data-iso='2026-10-01'" in html and "dir='ltr'" in html
    )
    # approved hidden by default, count stated, one-click control present
    assert "data-active='0'" in html and "הצג תכניות מאושרות (1)" in html
    assert "מוסתרות כברירת מחדל" in html
    # all filter controls + show-more present
    for cid in (
        "fq",
        "fstatus",
        "fflag",
        "fobj",
        "fappr",
        "ffrom",
        "fto",
        "freset",
        "more",
    ):
        assert f'id="{cid}"' in html
    # table comes before statistics
    assert html.find("<table") < html.find("סטטיסטיקה")


def test_status_chips_and_legend(tmp_path):
    rows = [
        _row("1", "הפקדה להתנגדויות"),
        _row("2", "אישור"),
        _row("3", "בבדיקה תכנונית"),
    ]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'class="chip c-deposit"' in html and 'class="chip c-approved"' in html
    assert 'class="chip c-review"' in html
    assert "מקרא סטטוסים" in html and html.find("legend") < html.find("<table")


def _permits(tmp_path, custom=None):
    import json

    reqs = {"requests": custom} if custom is not None else {
        "requests": [
            {
                "tik_num": "2026/0001.01",
                "address": "רחוב א 1",
                "mahut": "תוספת קומה",
                "sugbakasha": "היתר בניה",
                "status": "נפתח תיק רישוי",
                "status_date": "2026-09-01",
                "publication_start": "2026-10-01",
                "publication_end_planned": "2026-11-01",
                "gush": 30001,
                "helka": 5,
            },
            {
                "tik_num": "2024/0002.02",
                "address": "רחוב ב 2",
                "mahut": "שימוש חורג",
                "sugbakasha": "רישוי עסקים - שימוש חורג מתוכנית",
                "status": "הבקשה נסגרה",
                "status_date": "",
                "publication_start": "",
                "publication_end_planned": "",
                "gush": 30002,
                "helka": 6,
            },
        ]
    }
    pp = tmp_path / "permits.json"
    pp.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
    return str(pp)


def test_permits_filters_dates_default_active(tmp_path):
    from ginot import page

    rows = [
        _row(
            "1",
            "הפקדה להתנגדויות",
            recv="2026-10-01",
            dep="2026-10-10",
            deadline="2026-12-09",
        )
    ]
    page.render_site(rows, [], str(tmp_path), permits_path=_permits(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # dates render dd.mm.yy with ISO kept for filtering
    assert "01.10.26" in html and "data-iso='2026-10-01'" in html
    # active vs terminal flags: open file active, closed request terminal
    assert "data-active='1'" in html and "data-active='0'" in html
    # filter controls present, terminal hidden by default (checkbox unchecked)
    for cid in (
        "pfq",
        "pfstatus",
        "pfsug",
        "pffrom",
        "pfto",
        "pfclosed",
        "pfreset",
        "pfcount",
        "pmore",
    ):
        assert f'id="{cid}"' in html
    assert "הצג בקשות שהסתיימו (1)" in html
    assert "מוסתרות כברירת מחדל" in html
    # search text carries number/address/essence/type/gush/helka
    assert "2026/0001.01" in html and "גוש 30001" in html and "חלקה 5" in html
    # municipality SPA note, no invented per-request deep link
    assert "ykpubdata.jerusalem.muni.il" in html


def test_footer_links(tmp_path):
    from ginot import page

    page.render_site([_row("1", "אישור", recv="2019-05-02")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "github.com/reihlinstinct/ginot-hair-plans" in html
    assert 'href="about.html"' in html and "CONTRIBUTING.md" in html
    assert "<footer" in html


def test_status_legends_clickable(tmp_path):
    from ginot import page

    rows = [
        _row(
            "1",
            "הפקדה להתנגדויות",
            recv="2026-10-01",
            dep="2026-10-10",
            deadline="2026-12-09",
        ),
        _row("2", "אישור", recv="2019-05-02"),
    ]
    page.render_site(rows, [], str(tmp_path), permits_path=_permits(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # plans legend: raw-status chips; permits legend (#521): status-group
    # chips, objection groups selected by default, rest behind a disclosure
    assert "מקרא סטטוסים" in html
    assert '<b>סטטוסים:</b>' in html
    assert 'class="chip c-deposit" data-status="הפקדה להתנגדויות"' in html
    assert 'class="chip c-deposit sel" data-group="obj"' in html
    assert 'class="chip c-review sel" data-group="pre"' in html
    assert "סטטוסים נוספים" in html and "more-statuses" in html
    assert 'data-group="review"' in html and 'data-group="closed"' in html
    # permits group chips carry counts (fixture: נפתח תיק רישוי -> review)
    assert "בטיפול/דיונים (1)" in html and "סגור/אחר (1)" in html
    # raw status still filterable via the select and visible per row
    assert "data-status='נפתח תיק רישוי'" in html
    assert "data-status='הבקשה נסגרה'" in html
    assert "<option value='נפתח תיק רישוי'>" in html
    # click bindings for both tables
    assert ".plan-legend .chip" in html and "fstatus.value=(fstatus.value===st)" in html
    assert 'id="pfgroups"' in html and "selectedGroups" in html
    # #414: legend/options/counts derive from the loaded fragment client-side
    assert "rebuildDerived" in html and "statusClass" in html


def test_permit_status_chips(tmp_path):
    from ginot import page

    page.render_site(
        [_row("1", "אישור", recv="2019-05-02")],
        [],
        str(tmp_path),
        permits_path=_permits(tmp_path),
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # row status cells colour-coded like plan chips
    assert 'class="chip c-inproc"' in html  # נפתח תיק רישוי
    assert 'class="chip c-closed"' in html  # הבקשה נסגרה
    # legend group chips colour-coded and clickable; raw status stays on rows
    assert 'class="chip c-closed" data-group="closed"' in html
    assert 'class="chip c-inproc" data-group="review"' in html
    # mapping covers every live status value
    from ginot.page import _PERMIT_TERMINAL_STATUSES, _permit_status_class

    live = [
        "הבקשה נסגרה",
        "הופק-הוצא היתר בניה",
        "הוכנה טיוטת היתר בניה",
        "נדונה בוועדת המשנה",
        "התקבל תיק ורוד / מסמכים חתומים",
        "שולמה מקדמה",
        "נפתח תיק רישוי",
        "הופק היתר מוארך",
        "נדונה ברשות הרישוי",
        "ממתין לאישור נוסח פרסום",
        "נדונה בועדת ערר",
        "הגשה מקוונת הושלמה",
        "תחילת פרסום הבקשה להקלה",
        "תחילת הודעות לפני תקנה 36",
        "התקבל ערר",
    ]
    for st in live:
        cls = _permit_status_class(st)
        assert cls in (
            "c-closed",
            "c-approved",
            "c-deposit",
            "c-review",
            "c-cond",
            "c-inproc",
        ), st
    assert _permit_status_class("הבקשה נסגרה") == "c-closed"
    assert _permit_status_class("הופק-הוצא היתר בניה") == "c-approved"
    assert _permit_status_class("תחילת פרסום הבקשה להקלה") == "c-deposit"
    assert _permit_status_class("נדונה בועדת ערר") == "c-review"
    assert _permit_status_class("הוכנה טיוטת היתר בניה") == "c-cond"
    for st in _PERMIT_TERMINAL_STATUSES:
        assert _permit_status_class(st) in ("c-closed", "c-approved")


def test_permit_tik_number_deep_links_to_municipality_file(tmp_path):
    page.render_site(
        [_row("1", "אישור", recv="2019-05-02")],
        [],
        str(tmp_path),
        permits_path=_permits(tmp_path),
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # every request number links to the licensing file viewer (issue #96)
    assert (
        "href='https://ykpubdata.jerusalem.muni.il/#/Details?TikNum=2026%2F0001.01"
        "&SystemCode=26400046&Page=BakashalInfo' target='_blank'"
        " rel='noopener'>2026/0001.01</a>"
    ) in html
    from ginot.page import _permit_tik_link

    assert _permit_tik_link(None) == ""
    assert _permit_tik_link("") == ""
    assert "%2F" in _permit_tik_link("1910/0594.09")


def test_social_meta_tags_with_absolute_image(tmp_path):
    from ginot import page, preview

    rows = [
        {
            "pl_number": "1",
            "pl_name": "תכנית א",
            "station_desc": "הפקדה",
            "receiving_date": "2026-10-01",
            "pl_last_deposit_date": "2026-10-10",
            "depositing_date": "",
            "objection_deadline_derived_60d_from_publication": "2026-12-09",
            "pl_area_dunam": 3.2,
            "inside_flag": "inside",
            "mavat_url": "https://mavat.iplan.gov.il/x",
        }
    ]
    base = "https://example.org/site/"
    page.render_site(
        rows,
        [],
        str(tmp_path),
        base_url=base,
        council_geojson="data/council_ginot_hair.geojson",
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<meta property="og:title"' in html
    assert '<meta property="og:locale" content="he_IL">' in html
    assert '<meta name="description"' in html
    if (tmp_path / "og.png").exists():
        assert f'<meta property="og:image" content="{base}og.png">' in html
        assert '<meta name="twitter:card" content="summary_large_image">' in html
        from PIL import Image

        assert Image.open(tmp_path / "og.png").size == (1200, 630)
    else:  # no Pillow/font: no image tags (never point at a missing file)
        assert "og:image" not in html and preview._font(10) is None


def test_social_meta_has_no_image_tags_without_base_url(tmp_path):
    from ginot import page

    page.render_site([], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "og:image" not in html
    assert '<meta property="og:title"' in html


def test_preview_counts_open_objection_windows(tmp_path, monkeypatch):
    """Regression: the og card once showed 0 because rows were annotated only
    after the preview was drawn."""
    from ginot import page, preview

    seen = {}
    monkeypatch.setattr(
        preview,
        "render_preview",
        lambda rows, *a, **k: (
            seen.update(n=sum(1 for r in rows if r.get("_open_obj"))) or False
        ),
    )
    row = {
        "pl_number": "1",
        "pl_name": "תכנית א",
        "station_desc": "הפקדה להתנגדויות/השגות",
        "receiving_date": "2026-10-01",
        "pl_last_deposit_date": "2026-10-10",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "2999-12-09",
        "pl_area_dunam": 3.2,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }
    page.render_site([row], [], str(tmp_path))
    assert seen["n"] == 1


def test_css_is_external_file(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    html_out = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<style>" not in html_out
    assert '<link rel="stylesheet" href="style.css">' in html_out
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    assert "body{" in css and len(css) > 500


def _urgent_ul(html):
    import re

    return re.search(r'<ul id="urgent-list">(.*?)</ul>', html, re.DOTALL).group(1)


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


def test_inside_column_hidden_but_filterable(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # no visible inside/partial column (#162)
    assert 'data-sort="flag"' not in html and "בתוך/חלקי" not in html
    # ...but the filter select and the row attribute remain
    assert '<select id="fflag">' in html
    assert "data-flag='inside'" in html


def test_ai_review_column(tmp_path):
    r = _row(1, "הפקדה")
    r["pl_number"] = "101-1377753"
    reviews = {
        "101-1377753": "https://github.com/reihlinstinct/ginot-hair-plans/blob/main/plans/101-1377753/analysis/talking_points_101-1377753.md"
    }
    html = page.render_index(
        [r, _row(2, "הפקדה")], [], "2026-01-01", "גינות העיר", reviews=reviews
    )
    assert ">סקירת AI</th>" in html
    assert "talking_points_101-1377753.md" in html
    assert html.count("class='ai-review'") == 1  # only the plan that has a review
    # clearly labelled as AI-generated, not an official document
    assert "באמצעות AI" in html and "אינו מסמך רשמי" in html


def test_ai_review_links_discovered_from_plans_tree(tmp_path):
    pdir = tmp_path / "plans" / "101-1377753" / "analysis"
    pdir.mkdir(parents=True)
    (pdir / "talking_points_101-1377753.md").write_text(
        "# נקודות לדיון\n\n- שימור", encoding="utf-8"
    )
    r = _row(1, "הפקדה")
    r["pl_number"] = "101-1377753"
    out = tmp_path / "out"
    page.render_site([r], [], str(out), plans_dir=str(tmp_path / "plans"))
    html = (out / "index.html").read_text(encoding="utf-8")
    # owner decision 2026-10-21 (#177): link the rendered site page, not raw .md
    assert "reviews/talking_points_101-1377753.html" in html
    review = (out / "reviews" / "talking_points_101-1377753.html").read_text(
        encoding="utf-8"
    )
    assert 'dir="rtl"' in review and "<h1>" in review  # markdown rendered, RTL
    assert "סקירת AI" in review and "אינו מסמך רשמי" in review  # AI label
    assert "../index.html" in review  # back link
    assert "../style.css" in review  # site styling


def test_mobile_label_for_ai_review_column(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    assert '#plans td:nth-child(8)::before{content:"סקירת AI"}' in css
    assert "בתוך/חלקי" not in css


def test_stylesheet_uses_approved_ginothair_palette(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    # approved 2026-10-21 (#154): ginothair.org.il-inspired palette
    assert "#101f5b" in css and "#51b89a" in css and "#f3f6ff" in css
    assert "#c8a4de" in css and "#00a8cf" in css and "#6db633" in css
    # mobile sort-header chips stay readable (white bg, mint border, navy text)
    assert "#plans thead th{display:block;background:#fff" in css


def test_index_is_slim_and_full_rows_ship_as_rows_html(tmp_path):
    rows = [_row(i, "הפקדה") for i in range(1, 26)]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    rows_html = (tmp_path / "rows.html").read_text(encoding="utf-8")
    assert html.count("<tr class=''") == 20  # only the top rows are embedded (#164)
    assert rows_html.count("<tr class=''") == 25  # full set ships as a static asset
    assert "fetch('rows.html')" in html
    assert "<noscript>" in html and "20 התכניות המובילות" in html


def test_footer_github_link_text(tmp_path):
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # owner request 2026-10-21: link text is just "GitHub", target unchanged
    assert (
        '<a href="https://github.com/reihlinstinct/ginot-hair-plans">GitHub</a>' in html
    )
    assert ">github.com/reihlinstinct<" not in html


def test_permits_table_is_slim_and_full_set_ships_as_permits_html(tmp_path):
    permits = [
        {
            "tik_num": f"2020/{i:07d}",
            "status": "בבדיקה",
            "mahut": "x",
            "sugbakasha": "היתר",
            "gush": 1,
            "helka": i,
            "address": f"רחוב {i}",
            "status_date": "2026-09-01",
            "publication_start": "2026-09-05",
            "publication_end_planned": "",
        }
        for i in range(1, 26)
    ]
    pf = tmp_path / "permits.json"
    import json as _json

    pf.write_text(_json.dumps({"requests": permits}), encoding="utf-8")
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path), permits_path=str(pf))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    permits_html = (tmp_path / "permits.html").read_text(encoding="utf-8")
    assert html.count("2020/") < permits_html.count(
        "2020/"
    )  # only top rows embedded (#169)
    assert permits_html.count("<tr ") == 25
    assert "fetch('permits.html')" in html
    assert "<noscript>" in html and "20 הבקשות הראשונות" in html


def test_about_page_combines_sources_and_datasets(tmp_path):
    # owner request 2026-10-21: datasets move off index into the About page
    page.render_site([_row(1, "הפקדה")], [], str(tmp_path))
    about = (tmp_path / "about.html").read_text(encoding="utf-8")
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    redir = (tmp_path / "sources.html").read_text(encoding="utf-8")
    for source in ("iplan", "land.gov.il", 'מאב"ת', "רישוי", "geojson"):
        assert source in about, source
    assert "רענון שבועי" in about and "עודכן:" in about
    assert "יוזמה עצמאית" in about and "פרטיות" in about  # about content kept
    assert 'id="datasets-list"' in about and "fetch('index.json')" in about
    assert "מערכי נתונים" in about
    # index no longer carries the datasets section
    assert 'id="datasets-list"' not in html and "fetch('index.json')" not in html
    # footer links the combined page
    assert '<a href="about.html">אודות ומקורות נתונים</a>' in html
    # the short-lived sources.html URL stays valid as a redirect
    assert "url=about.html" in redir


def test_changes_section_renders_as_card(tmp_path):
    page.render_site(
        [_row(1, "הפקדה")],
        [
            {
                "kind": "new",
                "pl_number": "1",
                "pl_name": "x",
                "mavat_url": "https://mavat.iplan.gov.il/x",
            }
        ],
        str(tmp_path),
    )
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    css = (tmp_path / "style.css").read_text(encoding="utf-8")
    # owner request 2026-10-21: changes list sits in a card like the urgent row
    assert '<ul id="changes-list">' in html
    assert "#changes-list{background:#fff;border:1px solid #dde4f6" in css
    assert "border-radius:10px" in css


def test_open_json_and_api_section(tmp_path):
    import json

    rows = [
        _row(
            "1",
            "הפקדה להתנגדויות",
            recv="2026-10-01",
            dep="2026-10-10",
            deadline="2026-12-09",
        ),
        _row("2", "אישור", recv="2019-05-02"),
    ]
    page.render_site(rows, [], str(tmp_path))
    d = json.loads((tmp_path / "open.json").read_text(encoding="utf-8"))
    assert d["count"] == 1 and [p["pl_number"] for p in d["plans"]] == ["1"]
    assert "definition" in d and "generated" in d
    assert all("in_objection_period" in p for p in d["plans"])
    about = (tmp_path / "about.html").read_text(encoding="utf-8")
    assert "גישה לנתונים (API)" in about and "open.json" in about


def test_favicon_subpath_links_on_root_and_review():
    from ginot import page

    root = page.render_index([], [], "2026-10-22", "test")
    review = page.render_review("101-1", "# test", "2026-10-22", "test")
    for html, prefix in [(root, ""), (review, "../")]:
        assert f'href="{prefix}favicon.ico?v=20261022"' in html
        assert f'href="{prefix}favicon.svg?v=20261022"' in html
        assert f'href="{prefix}favicon-32.png?v=20261022"' in html
        assert f'href="{prefix}apple-touch-icon.png?v=20261022"' in html
        assert 'sizes="any"' in html


def test_favicon_committed_fallback_files_decode_at_expected_sizes():
    from pathlib import Path

    from PIL import Image

    root = Path(__file__).parent.parent / "docs"
    icon = Image.open(root / "favicon.ico")
    assert icon.format == "ICO"
    assert icon.info["sizes"] == {(16, 16), (32, 32), (48, 48)}
    for filename, size in [
        ("favicon-32.png", (32, 32)),
        ("apple-touch-icon.png", (180, 180)),
    ]:
        image = Image.open(root / filename)
        assert image.format == "PNG" and image.size == size
        image.verify()
    assert "<svg" in (root / "favicon.svg").read_text()


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

def test_permits_recency_markup(tmp_path):
    from ginot import page

    def p(tik, status, pub="", end=""):
        return {
            "tik_num": tik,
            "status": status,
            "mahut": "מ",
            "sugbakasha": "היתר",
            "address": "רחוב 1",
            "status_date": "",
            "publication_start": pub,
            "publication_end_planned": end,
        }

    reqs = [
        p("2020/1.01", "בבדיקה", pub="2026-10-01"),
        p("2020/2.01", "תום תקופת פרסום"),
        p("2020/3.01", "בבדיקה", end="2026-11-01"),
        p("2020/4.01", "בבדיקה"),
        p("2020/5.01", "בבדיקה", pub="2026-13-45"),
    ]
    page.render_site([], [], str(tmp_path), permits_path=_permits(tmp_path, reqs))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # categories land on rows for the client filter and the counters
    assert "data-pubcat='dated'" in html
    assert html.count("data-pubcat='pub-nodate'") == 2  # status + planned end
    assert html.count("data-pubcat='no-evidence'") == 2  # plain + malformed date
    # undated rows carry the visible marker
    assert html.count("pub-missing") >= 4
    assert "תאריך פרסום חסר" in html
    # split counters + invalid-date flag placeholders and the page note
    assert 'id="pfunknown"' in html and 'id="pfflag"' in html
    # #521: the default view is objection-group + scope based; the recency
    # date inputs stay but with no default cutoff (an open objection window
    # must never be hidden by an arbitrary 6-month rule)
    assert "הרלוונטיות להתנגדות" in html
    assert "rollingCutoff" not in html
    assert "pffrom.value=DEF_FROM" not in html


def test_iso_rejects_malformed_dates():
    from ginot import page

    assert page._iso("2026-10-18") == "2026-10-18"
    assert page._iso("2026-13-45") == ""  # impossible month/day
    assert page._iso("2026-00-10") == ""
    assert page._iso("18.10.2026") == ""
    assert page._iso(None) == ""

def test_permit_partial_address_display(tmp_path):
    # #408: a neighborhood name is never disguised as a street address
    from ginot import page

    def p(tik, **kw):
        row = {
            "tik_num": tik,
            "status": "בבדיקה",
            "mahut": "מ",
            "sugbakasha": "היתר",
        }
        row.update(kw)
        return row

    reqs = [
        p("1/1", rehovName="אלפסי", mispBait="9", schunaName="גינות העיר"),
        p("2/2", rehovName="", mispBait="", schunaName="גינות העיר"),
        p("3/3", rehovName="", mispBait="", schunaName=""),
        p("4/4", address="מחרוזת מדורת 7"),  # legacy row: no raw fields
    ]
    page.render_site([], [], str(tmp_path), permits_path=_permits(tmp_path, reqs))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # street present -> plain street address
    assert "<td>אלפסי 9 <span class='pub-missing'>אין מיקום</span></td>" in html
    # neighborhood only -> labeled neighborhood + explicit note
    assert "שכונה: גינות העיר" in html and "לא צוינה כתובת מדויקת בתיק" in html
    # neither -> explicit fallback, no invented value
    assert "כתובת לא זמינה" in html
    # legacy rows keep their stored address string as-is
    assert "<td>מחרוזת מדורת 7 <span class='pub-missing'>אין מיקום</span></td>" in html
    # neighborhood is searchable
    assert "גינות העיר" in html


def test_permit_status_group_mapping_covers_live_statuses():
    """#521: every status seen in the live feed maps to a defined group; an
    unknown future status fails VISIBLE into the default-selected 'unmapped'
    group (missing an objection window is worse than noise)."""
    from ginot.page import PERMIT_STATUS_GROUPS, _permit_status_group

    live = [
        "הופק-הוצא היתר בניה", "הוכנה טיוטת היתר בניה", "הבקשה נסגרה",
        "נדונה בוועדת המשנה", "התקבל תיק ורוד / מסמכים חתומים", "שולמה מקדמה",
        "נדונה ברשות הרישוי", "נפתח תיק רישוי", "הופק היתר מוארך",
        "נדונה בועדת ערר", "הגשה מקוונת הושלמה", "ממתין לאישור נוסח פרסום",
        'אושר ע"י מהנדס העיר', "תום תקופת פרסום", "חידוש טיפול בבקשה",
        "התקבל ערר", "הבקשה נגנזה", "תחילת פרסום הבקשה להקלה",
        "נוסח פרסום אושר", "", "השלמת הודעות לפני תקנה 36",
        "תחילת הודעות לפני תקנה 36", "פורסמה בקשה להקלה",
        "התקבלה בקשה לדיון המועצה",
    ]
    mapped = set()
    for _key, _label, statuses, _dv in PERMIT_STATUS_GROUPS:
        mapped |= statuses
    for st in live:
        assert st in mapped, st
    # every mapped status maps back to its own group
    assert _permit_status_group("תחילת פרסום הבקשה להקלה") == ("obj", "פתוח להתנגדויות", True)
    assert _permit_status_group("ממתין לאישור נוסח פרסום") == ("pre", "פרסום מתקרב", True)
    assert _permit_status_group("הבקשה נסגרה") == ("closed", "סגור/אחר", False)
    # unknown status: unmapped, default-visible
    key, label, default_visible = _permit_status_group("סטטוס חדש מהעירייה")
    assert (key, default_visible) == ("unmapped", True)
    assert label


def test_permit_scope_classification():
    """#521: scope flag by the 7 neighbourhoods; schunaName definitive, legacy
    address matched by trailing neighbourhood, no signal = unknown (visible)."""
    from ginot.page import _permit_scope

    assert _permit_scope({"schunaName": "קטמון הישנה"}) == "in"
    assert _permit_scope({"schunaName": "גוננים"}) == "out"
    assert _permit_scope({"address": "הפלמח 41 קטמון הישנה"}) == "in"
    assert _permit_scope({"address": "דרך עזה 42 רחביה"}) == "in"
    assert _permit_scope({"address": 'רשב"ג 52 גונן ב'}) == "out"
    assert _permit_scope({"address": "אלכסנדריון 12 גונן ג"}) == "out"
    assert _permit_scope({"address": "בר יוחאי 5-7"}) == "unknown"
    assert _permit_scope({"address": ""}) == "unknown"
    assert _permit_scope({}) == "unknown"


def test_permits_default_view_markup(tmp_path):
    """#521: rows carry data-group/data-scope; objection groups default-selected;
    scope + open-deadline checkboxes present with counts."""
    from ginot import page

    reqs = [
        {  # open objection, in scope -> default visible
            "tik_num": "2026/0439.00", "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ", "sugbakasha": "היתר", "address": "הפלמח 41 קטמון הישנה",
            "status_date": "", "publication_start": "2026-10-18",
            "publication_end_planned": "2026-11-24", "gush": 30007, "helka": 12,
        },
        {  # open objection, out of scope (גוננים)
            "tik_num": "2026/0223.00", "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ", "sugbakasha": "היתר", "address": "אלעזר בן יאיר 24 גוננים",
            "status_date": "", "publication_start": "2026-10-21",
            "publication_end_planned": "2026-11-29", "gush": 30143, "helka": 5,
        },
        {  # objection group but window closed -> hidden while pfopenonly on
            "tik_num": "2024/0211.03", "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ", "sugbakasha": "היתר", "address": "יוסי בן יועזר 36 גוננים",
            "status_date": "", "publication_start": "2026-09-17",
            "publication_end_planned": "2026-10-04", "gush": 30143, "helka": 9,
        },
        {  # non-objection group, in scope
            "tik_num": "2020/0001.01", "status": "נפתח תיק רישוי",
            "mahut": "מ", "sugbakasha": "היתר", "address": "אלפסי 9 רחביה",
            "status_date": "", "publication_start": "", "publication_end_planned": "",
            "gush": 30001, "helka": 3,
        },
    ]
    page.render_site([], [], str(tmp_path), permits_path=_permits(tmp_path, reqs))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "data-group='obj' data-scope='in'" in html
    assert html.count("data-group='obj' data-scope='out'") == 2
    assert "data-group='review' data-scope='in'" in html
    # objection groups default-selected, others behind the disclosure
    assert 'data-group="obj" data-default=\'1\'' in html
    assert 'data-group="pre" data-default=\'1\'' in html
    assert 'data-group="review" data-default' not in html
    assert "סטטוסים נוספים" in html
    # new filter controls with live counts
    assert 'id="pfopenonly" checked' in html
    assert 'id="pfscope"' in html and "הצג גם מחוץ ל-7 השכונות (2)" in html
    # JS applies the deadline check only to the obj group against Jerusalem today
    assert "todayJL" in html and "pe<TODAY" in html
    assert "data-scope')==='out'" in html


def test_permit_enrichment_coverage_panel_is_aggregate_and_honest():
    from ginot.page import _PERMITS_JS, _permits_section

    html = _permits_section([{"tik_num": "2026/0001.00", "status": "נפתח תיק רישוי"}])
    assert 'id="permit-coverage"' in html
    assert 'id="permit-coverage-counts"' in html
    assert "סיום פרסום מתוכנן אינו מועד התנגדות מאומת" in html
    assert "תאריך פרסום חסר אינו מעיד שלא פורסמה בקשה" in html
    assert "לפני סינון התצוגה" in html
    assert "rows.length-dated" in _PERMITS_JS
    assert "getAttribute('data-pubend')" in _PERMITS_JS


def test_coverage_inline_full_set_and_invalid_dates():
    from ginot.page import _PERMITS_JS, _permits_section

    rows = [{"tik_num": str(i), "status": "נפתח תיק רישוי"} for i in range(25)]
    rows[0]["publication_start"] = "2026-02-31"
    rows[1]["publication_start"] = "2026-02-28"
    rows[1]["publication_end_planned"] = "2026-04-31"
    html = _permits_section(rows)
    assert "25 בקשות במאגר; 1 עם תאריך תחילת פרסום; 0 עם סיום פרסום מתוכנן" in html
    assert "24 ללא תאריך תחילת פרסום" in html
    assert "if(validIso(rows[i].getAttribute('data-pub')||''))dated++" in _PERMITS_JS


def test_permit_ids_rewritten_when_permit_list_is_empty(tmp_path):
    """Regression (#530): with zero permit requests, render_site must still
    rewrite permit-ids.json. Otherwise the previous ids stay published and the
    submit worker keeps accepting reviews for requests no longer listed."""
    import json

    (tmp_path / "permit-ids.json").write_text(
        '{"ids":["2026/0439.00"]}\n', encoding="utf-8"
    )
    permits = tmp_path / "permit_requests.json"
    permits.write_text('{"requests": []}', encoding="utf-8")
    page.render_site([_row("1", "אישור")], [], str(tmp_path), permits_path=str(permits))
    ids = json.loads((tmp_path / "permit-ids.json").read_text(encoding="utf-8"))
    assert ids == {"ids": []}


def test_urgent_list_includes_permits_with_official_precedence():
    from ginot.page import _JS, _PERMITS_JS

    assert "#permits-table tbody tr" in _JS
    assert "data-scope')==='out'" in _JS
    assert "official||(validDeadline(planned)?planned:'')" in _JS
    assert "סיום פרסום מתוכנן (לא מאומת)" in _JS
    assert "מועד התנגדות (פרסום עירוני)" in _JS
    assert "window.__renderUrgent" in _PERMITS_JS


def test_render_site_removes_stale_official_projection(tmp_path):
    from ginot.page import render_site

    source = tmp_path / 'input'
    source.mkdir()
    permits_path = source / 'permit_requests.json'
    permits_path.write_text('{"requests": []}')
    publications_path = source / 'publications_active.json'
    publications_path.write_text('[{"tik_num": "2026/0439.00", "in_polygon": true, '
                                 '"objection_deadline": "2026-11-13", "private_note": "omit"}]')
    out = tmp_path / 'site'
    render_site([], [], str(out), permits_path=str(permits_path))
    projection = out / 'publications_active.json'
    import json
    assert json.loads(projection.read_text()) == [{
        'tik_num': '2026/0439.00', 'in_polygon': True, 'objection_deadline': '2026-11-13', 'publication_date': None}]
    publications_path.unlink()
    render_site([], [], str(out), permits_path=str(permits_path))
    assert not projection.exists()


def _subset_permit(tik, status, schuna="קטמון הישנה"):
    return {"tik_num": tik, "status": status, "schunaName": schuna}


def test_default_permit_subset_holds_default_candidates_and_evidence_rows(tmp_path):
    """#441: the eagerly loaded subset must contain every row the default view,
    the urgency list (#522) or the publication overlay (#573) can need."""
    from ginot import page

    obj, pre = "תחילת פרסום הבקשה להקלה", "נוסח פרסום אושר"
    permits = [
        _subset_permit("2026/0001.00", obj),
        _subset_permit("2026/0002.00", pre),
        _subset_permit("2026/0003.00", obj, schuna="גילה"),  # out of scope
        _subset_permit("2026/0004.00", "הבקשה נסגרה"),  # terminal
        _subset_permit("2026/0005.00", "תום תקופת פרסום"),  # non-default group
        _subset_permit("2026/0006.00", "תום תקופת פרסום"),  # ... with evidence
        _subset_permit("2026/0007.00", "סטטוס חדש שלא מופה"),  # unmapped: visible
        _subset_permit("2026/0008.00", "הבקשה נסגרה"),  # terminal, evidence anyway
    ]
    full, subset = tmp_path / "permits.html", tmp_path / "permits-default.html"
    page._permits_section(
        permits,
        rows_file=str(full),
        default_rows_file=str(subset),
        evidence_tiks=frozenset({"2026/0006.00", "2026/0008.00"}),
    )
    body = subset.read_text(encoding="utf-8")
    included = {t for t in (p["tik_num"] for p in permits) if f"data-tik='{t}'" in body}
    assert included == {"2026/0001.00", "2026/0002.00", "2026/0006.00", "2026/0007.00"}
    # Every subset row is byte-identical to its row in the full fragment.
    full_rows = set(full.read_text(encoding="utf-8").split("</tr>"))
    assert all(r in full_rows for r in body.split("</tr>"))
