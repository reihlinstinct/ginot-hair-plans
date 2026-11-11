"""Browser coverage: permits. Shared fixtures stay in test_site_browser."""

import datetime
import functools
import http.server
import json
import pathlib
import shutil
import sys
import threading

import pytest
from test_site_browser import FEATURES, ROOT, _d, _Quiet, _ThreadingServer, plan_ids

from ginot import i18n, refresh
from ginot.dates import today_il

pytest_plugins = ["test_site_browser"]


# Section: Permits


def test_permits_default_hides_closed_and_counts(page):
    assert page.locator("#permits-table tbody tr").count() == 10
    # 8 visible (#521 default: objection-relevant groups selected, no recency
    # cutoff): hidden are the terminal row (closed group, also data-active=0)
    # and the post-publication row (group behind "סטטוסים נוספים").
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 8
    assert page.locator("#pfcount").inner_text() == "מציג 8 מתוך 8"
    # "הצג בקשות שהסתיימו" selects the closed+issued group chips and reveals
    # the terminal row.
    page.check("#pfclosed")
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 9


def test_permit_search_and_status_select(page):
    page.fill("#pfq", "אלפסי")
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
    page.click("#pfreset")
    # #521: legend chips are status GROUPS; a raw status is picked in the select.
    page.select_option("#pfstatus", "בבדיקה")
    assert page.locator("#pfstatus").input_value() == "בבדיקה"
    # 0439.00, 0001, 0002, 0004, 0005, 0007, 0009 (no recency cutoff since #521)
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 7


def test_permit_publication_date_filter(page):
    # Manual from-date filters DATED rows only; undated rows stay visible
    # (design option A: the recency filter never hides date-unknown rows).
    page.fill("#pffrom", _d(-10))
    vis = page.locator("#permits-table tbody tr:not(.filtered-out)")
    # 6: the post-publication row sits in a default-off group since #521.
    assert vis.count() == 6
    assert vis.filter(has_text="2020/0001.01").count() == 0  # dated, before from
    assert vis.filter(has_text="2020/0002.01").count() == 1  # undated, survives
    assert vis.filter(has_text="2026/0439.00").count() == 1  # dated, after from


def test_permits_no_recency_default_and_manual_date_filter(page):
    # #521: the rolling six-month default was removed - it hid open תקנה 36
    # windows. The from input starts empty, every dated row is visible by
    # default (subject to the group chips), date-unknown rows stay visible
    # and marked, and a typed from-date still narrows dated rows only.
    assert page.locator("#pffrom").input_value() == ""
    vis = page.locator("#permits-table tbody tr:not(.filtered-out)")
    assert vis.filter(has_text="2020/0004.01").count() == 1  # pre-window dated: visible
    assert vis.filter(has_text="2026/0439.00").count() == 1  # regression
    assert vis.filter(has_text="2020/0005.01").count() == 1  # future date
    # undated rows visible with the marker
    assert page.locator("#permits-table .pub-missing").count() >= 3
    # split date-unknown counters over VISIBLE rows: 0007 is pub-nodate
    # (0006 too, but its post-publication group is off by default), 3 no-evidence
    assert (
        page.locator("#pfunknown").inner_text()
        == "תאריך פרסום חסר: 1 (פורסם, תאריך לא ידוע) · 3 (אין ראיית פרסום)"
    )
    # A typed from-date narrows dated rows; reset restores the empty default.
    page.fill("#pffrom", _d(-10))
    assert (
        page.locator("#permits-table tbody tr:not(.filtered-out)")
        .filter(has_text="2020/0004.01")
        .count()
        == 0
    )
    page.click("#pfreset")
    assert page.locator("#pffrom").input_value() == ""
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 8


def test_permits_default_sort_dated_desc_undated_last(page):
    # #451: default order is dated rows newest-first, then date-unknown rows
    # in their own honest placement (pub-nodate before no-evidence), stable
    # tik number order inside each equal-date group (#676). Since #521 there is no recency cutoff, so
    # the pre-window dated row (0004) is in the default view too; the
    # post-publication row (0006) is hidden by its default-off group chip.
    ids = page.locator(
        "#permits-table tbody tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    assert ids[:4] == ["2020/0005.01", "2026/0439.00", "2020/0001.01", "2020/0004.01"]
    assert ids[4] == "2020/0007.01"
    assert ids[5:] == ["2020/0002.01", "2020/0008.01", "2020/0009.01"]
    # A typed from-date narrows without disturbing the dated-desc order.
    page.fill("#pffrom", _d(-20))
    narrow = page.locator(
        "#permits-table tbody tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    assert narrow[:2] == ["2020/0005.01", "2026/0439.00"]
    assert "2020/0001.01" not in narrow


def test_permit_deep_links_point_to_municipality_file(page):
    links = page.locator("#permits-table tbody tr td:first-child a")
    assert links.count() == 10
    # Order-independent since #451 (default sort is dated-desc): pick the
    # 0439 row explicitly instead of assuming it is first.
    link = page.locator(
        "#permits-table tbody tr td:first-child a", has_text="2026/0439.00"
    )
    href = link.get_attribute("href")
    assert href == (
        "https://ykpubdata.jerusalem.muni.il/#/Details?TikNum=2026%2F0439.00"
        "&SystemCode=26400046&Page=BakashalInfo"
    )
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in link.get_attribute("rel")


def test_permit_closed_checkbox_is_explicit_and_does_not_change_plan_filter(page):
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 0
    before = plan_ids(page)
    # #521: the closed raw-status chip is gone; the "הצג בקשות שהסתיימו"
    # checkbox reveals terminal rows by selecting the closed+issued group chips.
    page.check("#pfclosed")
    assert "sel" in (
        page.locator("#permits .legend .chip[data-group='closed']").get_attribute(
            "class"
        )
    )
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 1
    assert page.locator("#fstatus").input_value() == ""
    assert plan_ids(page) == before
    page.click("#pfreset")
    assert "sel" not in (
        page.locator("#permits .legend .chip[data-group='closed']").get_attribute(
            "class"
        )
    )
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 0


def test_committed_site_includes_permit_filter_script():
    html = (ROOT / "docs/index.html").read_text()
    assert "window.__permitsLoaded=true" in html
    assert "document.getElementById('pfstatus')" in html


def test_committed_permit_legend_cannot_trigger_plan_listener():
    html = (ROOT / "docs/index.html").read_text()
    assert "plegend" not in html
    assert html.count('class="legend plan-legend"') == 1
    assert html.count('name="twitter:title"') == 1


@pytest.fixture(scope="module")
def real_site(tmp_path_factory):
    """Site built from the REAL feed (data/permit_requests.json) - #451
    requires proving the sort surfaces 2026/0439.00 inside the default
    20-row view on the real 11k-row dataset, not only on fixtures."""
    tmp = tmp_path_factory.mktemp("realsite")
    cwd = pathlib.Path.cwd()
    (tmp / "data").mkdir()
    shutil.copy(
        ROOT / "data" / "council_ginot_hair.geojson", tmp / "data" / "council.geojson"
    )
    shutil.copy(
        ROOT / "data" / "permit_requests.json", tmp / "data" / "permit_requests.json"
    )
    shutil.copytree(ROOT / "docs", tmp / "docs", ignore=shutil.ignore_patterns("badge"))
    mp = pytest.MonkeyPatch()
    mp.chdir(tmp)
    mp.setattr(
        refresh.iplan,
        "query_plans",
        lambda council, service="x", **kw: (
            FEATURES if service == "xplan_without_77_78" else []
        ),
    )
    mp.setattr(
        sys,
        "argv",
        [
            "ginot.refresh",
            "--council",
            "data/council.geojson",
            "--out",
            "out",
            "--site",
            "docs",
            "--snapshots",
            "snapshots",
            "--status",
            "data/plan_status.json",
        ],
    )
    refresh.main()
    mp.undo()
    assert pathlib.Path.cwd() == cwd
    return tmp / "docs"


@pytest.fixture(scope="module")
def real_served(real_site):
    handler = functools.partial(_Quiet, directory=str(real_site))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}"


def test_real_dataset_0439_in_default_visible_20(browser, real_served):
    # No evidence capture here: the real dataset renders ~11k rows and a
    # full-page screenshot would be enormous; the assertion is in-page JS.
    ctx = browser.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        pg.goto(real_served + "/index.html")
        # #441: the full list loads on demand; these tests need all rows.
        pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
        pg.wait_for_function(
            "window.__permitsLoaded === true || window.__permitsFailed === true",
            timeout=180000,
        )
        assert pg.evaluate("window.__permitsLoaded") is True, (
            "permits.html failed to load"
        )
        res = pg.evaluate(
            "(function(){"
            "var vis=[].slice.call(document.querySelectorAll("
            "'#permits-table tbody tr:not(.filtered-out)'));"
            "var inFirst=vis.slice(0,20).some(function(r){"
            "return (r.getAttribute('data-search')||'').indexOf('2026/0439.00')!==-1;});"
            "var dated=vis.filter(function(r){return r.getAttribute('data-pub');});"
            "var desc=dated.every(function(r,i){"
            "return !i||dated[i-1].getAttribute('data-pub')>=r.getAttribute('data-pub');});"
            "var firstUndated=vis.findIndex(function(r){return !r.getAttribute('data-pub');});"
            "var lastDated=-1;vis.forEach(function(r,i){"
            "if(r.getAttribute('data-pub'))lastDated=i;});"
            "return {total:vis.length,dated:dated.length,inFirst:inFirst,"
            "desc:desc,firstUndated:firstUndated,lastDated:lastDated};})()"
        )
        # The default view is capped at 20 visible rows; since #521 the default
        # pre-selects the objection-relevant groups in the 7 neighbourhoods, so
        # the matching set is the objection workload, not the whole feed.
        import re as _re

        m = _re.search(r"מציג 20 מתוך ([0-9]+)", pg.locator("#pfcount").inner_text())
        assert m and int(m.group(1)) >= 20, pg.locator("#pfcount").inner_text()
        assert res["inFirst"], (
            "2026/0439.00 is not inside the default-visible 20 on the real"
            f" dataset: {res}"
        )
        assert res["desc"], f"dated rows are not newest-first: {res}"
        assert res["firstUndated"] == -1 or res["lastDated"] < res["firstUndated"], res
        assert errors == [], f"JavaScript errors on the page: {errors}"
    finally:
        ctx.close()


@pytest.mark.parametrize(
    "official,expected_date,expected_label,expiry",
    [
        ("2026-11-13", "13.11.2026", "מועד התנגדות (פרסום עירוני)", "2026-11-14"),
        ("2026-02-30", "24.11.2026", "סיום פרסום מתוכנן (לא מאומת)", "2026-11-25"),
        ("not-a-date", "24.11.2026", "סיום פרסום מתוכנן (לא מאומת)", "2026-11-25"),
    ],
)
def test_urgent_permits_official_date_overrides_planned(
    tmp_path, browser, official, expected_date, expected_label, expiry
):
    from ginot.page import render_site

    permits = [
        {
            "tik_num": "2026/0439.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "address": "הפלמח 41 קטמון הישנה",
            "publication_end_planned": "2026-11-24",
        }
    ]
    source = tmp_path / "input"
    source.mkdir()
    (source / "permit_requests.json").write_text(json.dumps({"requests": permits}))
    (source / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0439.00",
                    "in_polygon": True,
                    "objection_deadline": official,
                }
            ]
        )
    )
    out = tmp_path / "site"
    render_site([], [], str(out), permits_path=str(source / "permit_requests.json"))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(out)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{server.server_port}/?today=2026-10-26")
        page.wait_for_function(
            "window.__permitsDefaultLoaded && window.__permitOfficialDeadlines"
        )
        text = page.locator("#urgent-list").inner_text()
        assert "2026/0439.00" in text
        assert expected_date in text
        assert expected_label in text
        if official == "2026-11-13":
            assert "24.11.2026" not in text
        page.goto(f"http://127.0.0.1:{server.server_port}/?today={expiry}")
        page.wait_for_function(
            "window.__permitsDefaultLoaded && window.__permitOfficialDeadlines"
        )
        assert "2026/0439.00" not in page.locator("#urgent-list").inner_text()
    finally:
        server.shutdown()


def test_tel_hai_publication_visible_despite_stale_feed_status(tmp_path, browser):
    from ginot.page import render_site

    source = tmp_path / "source"
    source.mkdir()
    (source / "permit_requests.json").write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "tik_num": "1975/0743.02",
                        "status": "שולמה מקדמה",
                        "address": "תל חי 4 קטמון הישנה",
                        "publication_start": "",
                        "publication_end_planned": "",
                    }
                ]
            }
        )
    )
    (source / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "1975/0743.02",
                    "in_polygon": True,
                    "publication_date": "2026-10-26",
                    "objection_deadline": None,
                }
            ]
        )
    )
    out = tmp_path / "site"
    render_site([], [], str(out), permits_path=str(source / "permit_requests.json"))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(out)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    page = browser.new_page()
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}/")
        page.wait_for_function(
            "window.__permitsDefaultLoaded && window.__permitPublicationEvidenceLoaded"
        )
        page.locator("#pfq").fill("תל חי 4")
        page.wait_for_function(
            "window.__permitsLoaded"
        )  # #441: search loads the full list
        row = page.locator('tr[data-tik="1975/0743.02"]')
        assert row.is_visible()
        assert "פרסום עירוני" in row.inner_text()
        assert "מועד התנגדות לא ידוע - יש לבדוק בפרסום העירוני" in row.inner_text()
        assert "שולמה מקדמה" in row.inner_text()
        assert row.get_attribute("data-pub") == "2026-10-26"
        assert row.get_attribute("data-pubend") == ""
        assert page.locator("#pfcount").inner_text() == "מציג 1 מתוך 1"
    finally:
        page.close()
        server.shutdown()


@pytest.mark.parametrize("official_deadline", [True, False])
def test_publication_group_explains_raw_status_and_exact_filter(
    tmp_path, browser, official_deadline
):
    """#882: publication evidence can include a different raw status, visibly."""
    from ginot.page import render_site

    source = tmp_path / "source"
    source.mkdir()
    requests = [
        {
            "tik_num": "2000/0001.00",
            "status": "שולמה מקדמה",
            "address": "רחביה",
            "publication_start": "",
            "publication_end_planned": (
                today_il() + datetime.timedelta(days=2)
            ).isoformat(),
        },
        {
            "tik_num": "2000/0002.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "address": "רחביה",
            "publication_start": today_il().isoformat(),
            "publication_end_planned": "",
        },
    ]
    (source / "permit_requests.json").write_text(json.dumps({"requests": requests}))
    (source / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2000/0001.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": (
                        (today_il() + datetime.timedelta(days=3)).isoformat()
                        if official_deadline
                        else None
                    ),
                }
            ]
        )
    )
    out = tmp_path / "site"
    render_site([], [], str(out), permits_path=str(source / "permit_requests.json"))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(out)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pg = browser.new_page()
    try:
        pg.goto(f"http://127.0.0.1:{server.server_port}/")
        pg.wait_for_function(
            "window.__permitsDefaultLoaded && window.__permitPublicationEvidenceLoaded"
        )
        row = pg.locator('tr[data-tik="2000/0001.00"]')
        assert row.is_visible()
        assert row.get_attribute("data-status") == "שולמה מקדמה"
        assert row.get_attribute("data-group") == "pubcheck"
        assert "קבוצת התצוגה נקבעת לפי הפרסום" in row.inner_text()
        if official_deadline:
            assert "אפשרות הגשה לא אומתה" in pg.locator("#urgent-list").inner_text()
            assert (
                "פרסום עירוני - דורש בדיקה" in pg.locator("#urgent-list").inner_text()
            )
        else:
            assert "2000/0001.00" not in pg.locator("#urgent-list").inner_text()
            assert "מועד התנגדות לא ידוע" in row.inner_text()
        assert (
            pg.locator('#pfgroups .chip[data-group="pubcheck"]').inner_text()
            == "פרסום עירוני - דורש בדיקה"
        )
        assert "לא לפי סטטוס מדויק" in pg.locator("#permit-group-help").inner_text()
        assert (
            "פרסום / הודעות להתנגדות"
            in pg.locator('#pfgroups .chip[data-group="obj"]').inner_text()
        )
        # The two groups are independent: paid advance is not in objection group.
        pg.locator('#pfgroups .chip[data-group="pubcheck"]').click()
        pg.wait_for_function("window.__permitsLoaded === true")
        assert not row.is_visible()
        assert pg.locator('tr[data-tik="2000/0002.00"]').is_visible()
        pg.locator('#pfgroups .chip[data-group="pubcheck"]').click()
        assert row.is_visible()
        pg.locator("#pfstatus").select_option("תחילת פרסום הבקשה להקלה")
        pg.wait_for_function("window.__permitsLoaded === true")
        assert not row.is_visible()
        assert pg.locator('tr[data-tik="2000/0002.00"]').is_visible()
        pg.locator("#pfstatus").select_option("שולמה מקדמה")
        assert row.is_visible()
        assert not pg.locator('tr[data-tik="2000/0002.00"]').is_visible()
    finally:
        pg.close()
        server.shutdown()


# Section: Direct fragment navigation


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_permits_fragment_opens_the_index_section(browser, served, code):
    # The rows fragments are data files the index injects with innerHTML;
    # opened directly (a shared link, a search hit) they used to render as an
    # unstyled wall of rows (user report 2026-11-11). The guard at the top of
    # each fragment redirects top-level navigation to the index's permits
    # section; innerHTML injection never runs it, so table loads still work.
    pg = browser.new_page()
    try:
        pg.goto(served + "/" + i18n.page_path(code, "permits.html"))
        pg.wait_for_url("**/" + i18n.page_path(code, "index.html") + "#permits")
        pg.wait_for_selector("#permits-table tbody tr")
        assert pg.locator("#permits-table tbody tr").count() > 0
        assert pg.evaluate("document.styleSheets.length") > 0
    finally:
        pg.close()
