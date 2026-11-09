from ginot import page

# Section: Permits fixtures


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


def _permits(tmp_path, custom=None):
    import json

    reqs = (
        {"requests": custom}
        if custom is not None
        else {
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
    )
    pp = tmp_path / "permits.json"
    pp.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
    return str(pp)


def _subset_permit(tik, status, schuna="קטמון הישנה"):
    return {"tik_num": tik, "status": status, "schunaName": schuna}


# Section: Permits behavior


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
        "הופק-הוצא היתר בניה",
        "הוכנה טיוטת היתר בניה",
        "הבקשה נסגרה",
        "נדונה בוועדת המשנה",
        "התקבל תיק ורוד / מסמכים חתומים",
        "שולמה מקדמה",
        "נדונה ברשות הרישוי",
        "נפתח תיק רישוי",
        "הופק היתר מוארך",
        "נדונה בועדת ערר",
        "הגשה מקוונת הושלמה",
        "ממתין לאישור נוסח פרסום",
        'אושר ע"י מהנדס העיר',
        "תום תקופת פרסום",
        "חידוש טיפול בבקשה",
        "התקבל ערר",
        "הבקשה נגנזה",
        "תחילת פרסום הבקשה להקלה",
        "נוסח פרסום אושר",
        "",
        "השלמת הודעות לפני תקנה 36",
        "תחילת הודעות לפני תקנה 36",
        "פורסמה בקשה להקלה",
        "התקבלה בקשה לדיון המועצה",
    ]
    mapped = set()
    for _key, _label, statuses, _dv in PERMIT_STATUS_GROUPS:
        mapped |= statuses
    for st in live:
        assert st in mapped, st
    # every mapped status maps back to its own group
    assert _permit_status_group("תחילת פרסום הבקשה להקלה") == (
        "obj",
        "פרסום / הודעות להתנגדות",
        True,
    )
    assert _permit_status_group("ממתין לאישור נוסח פרסום") == (
        "pre",
        "פרסום מתקרב",
        True,
    )
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
            "tik_num": "2026/0439.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ",
            "sugbakasha": "היתר",
            "address": "הפלמח 41 קטמון הישנה",
            "status_date": "",
            "publication_start": "2026-10-18",
            "publication_end_planned": "2026-11-24",
            "gush": 30007,
            "helka": 12,
        },
        {  # open objection, out of scope (גוננים)
            "tik_num": "2026/0223.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ",
            "sugbakasha": "היתר",
            "address": "אלעזר בן יאיר 24 גוננים",
            "status_date": "",
            "publication_start": "2026-10-21",
            "publication_end_planned": "2026-11-29",
            "gush": 30143,
            "helka": 5,
        },
        {  # objection group but window closed -> hidden while pfopenonly on
            "tik_num": "2024/0211.03",
            "status": "תחילת פרסום הבקשה להקלה",
            "mahut": "מ",
            "sugbakasha": "היתר",
            "address": "יוסי בן יועזר 36 גוננים",
            "status_date": "",
            "publication_start": "2026-09-17",
            "publication_end_planned": "2026-10-04",
            "gush": 30143,
            "helka": 9,
        },
        {  # non-objection group, in scope
            "tik_num": "2020/0001.01",
            "status": "נפתח תיק רישוי",
            "mahut": "מ",
            "sugbakasha": "היתר",
            "address": "אלפסי 9 רחביה",
            "status_date": "",
            "publication_start": "",
            "publication_end_planned": "",
            "gush": 30001,
            "helka": 3,
        },
    ]
    page.render_site([], [], str(tmp_path), permits_path=_permits(tmp_path, reqs))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "data-group='obj' data-scope='in'" in html
    assert html.count("data-group='obj' data-scope='out'") == 2
    assert "data-group='review' data-scope='in'" in html
    # objection groups default-selected, others behind the disclosure
    assert "data-group=\"obj\" data-default='1'" in html
    assert "data-group=\"pre\" data-default='1'" in html
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


def test_publication_evidence_tiks_reads_in_polygon_entries_only(tmp_path):
    """#441: only entries the #573 overlay can promote (in_polygon is True)
    count, with no date filter; a missing or invalid list is no evidence."""
    import json

    from ginot.page import publication_evidence_tiks

    path = tmp_path / "publications_active.json"
    path.write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0001.00",
                    "in_polygon": True,
                    "publication_date": "2020-01-01",
                },
                {
                    "tik_num": "2026/0002.00",
                    "in_polygon": None,
                    "publication_date": "2026-10-01",
                },
                {
                    "tik_num": "2026/0003.00",
                    "in_polygon": "true",
                    "publication_date": "2026-10-01",
                },
                {"tik_num": "", "in_polygon": True},
                {"in_polygon": True},
                "not-an-object",
            ]
        ),
        encoding="utf-8",
    )
    assert publication_evidence_tiks(str(path)) == frozenset({"2026/0001.00"})
    assert publication_evidence_tiks(str(tmp_path / "missing.json")) == frozenset()
    path.write_text("{", encoding="utf-8")
    assert publication_evidence_tiks(str(path)) == frozenset()
    path.write_text("{}", encoding="utf-8")
    assert publication_evidence_tiks(str(path)) == frozenset()


def test_rejected_permit_is_terminal_but_preserved_in_all_rows(tmp_path):
    """Owner decision #809 hides rejected requests, never deletes history."""
    import json

    permits = tmp_path / "rejected.json"
    permits.write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "tik_num": "2026/0999.01",
                        "status": "נדחתה",
                        "address": "רחוב לבדיקה 1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page.render_site([_row("1", "אישור")], [], str(tmp_path), permits_path=str(permits))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "data-active='0' data-status='נדחתה'" in html
    assert "data-tik='2026/0999.01' data-group='closed'" in html
    assert "הצג בקשות שהסתיימו (1)" in html
    assert page._permit_status_class("נדחתה") == "c-closed"
    # The full history is retained while the initial active subset is empty.
    all_rows = (tmp_path / "permits.html").read_text(encoding="utf-8")
    assert "2026/0999.01" in all_rows
    default_rows = (tmp_path / "permits-default.html").read_text(encoding="utf-8")
    assert "2026/0999.01" not in default_rows
