"""Headless-browser tests of the built site (issue #106).

The site is built by the real pipeline (ginot.refresh) from a fixed synthetic
dataset, then opened in Chromium via Playwright and driven like a user:
filters, legend chips, sorting, the active-only default, dd.mm.yy dates,
permit deep links, footer/About links and expected row counts.

Skipped when Playwright or its browser is not installed (the CI
"site-browser" job installs both).
"""

import datetime
import functools
import http.server
import json
import pathlib
import re
import shutil
import socketserver
import sys
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

import evidence  # issue #422: per-test E2E evidence capture

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from ginot import refresh
from ginot.dates import today_il

# The page's "today" is Asia/Jerusalem (_todayIL); fixtures use the same clock.
TODAY = today_il()
MS_DAY = 86400 * 1000


def ms(d):
    return int(
        datetime.datetime(
            d.year, d.month, d.day, tzinfo=datetime.timezone.utc
        ).timestamp()
        * 1000
    )


def feat(num, status, advertise=None, name=None):
    a = {
        "pl_number": num,
        "pl_name": name or f"תכנית {num}",
        "station_desc": status,
        "receiving_date": ms(datetime.date(2026, 1, 15)),
        "pl_area_dunam": 2.5,
        "pl_url": f"https://mavat.iplan.gov.il/{num}",
    }
    if advertise:
        a["pl_date_advertise"] = ms(advertise)
    return {"attributes": a, "geometry": None}


# 22 deposit plans (open objection windows, deadlines spread over the next
# 22 days), 4 under review, 3 approved (hidden by default) = 29 plans,
# 26 of them active.
DEPOSIT = [
    feat(f"200-{i}", "הפקדה להתנגדויות", TODAY + datetime.timedelta(days=i - 50))
    for i in range(1, 23)
]
REVIEW = [feat(f"300-{i}", "בדיקה תכנונית") for i in range(1, 5)]
APPROVED = [feat(f"400-{i}", "אישור") for i in range(1, 4)]
FEATURES = DEPOSIT + REVIEW + APPROVED


def _permit(tik, status, address, pub=None, end=None):
    p = {
        "tik_num": tik,
        "status": status,
        "mahut": "תוספת בניה",
        "sugbakasha": "היתר",
        "gush": 30000,
        "helka": 12,
        "address": address,
        "status_date": "2026-09-01",
        "publication_start": pub if pub is not None else "",
        "publication_end_planned": end if end is not None else "",
    }
    return p


def _d(days):
    return (TODAY + datetime.timedelta(days=days)).isoformat()


# Recency-filter fixture (design permit-recency-filter): every category of
# the publication-date world is represented, dates relative to TODAY so the
# rolling six-month default never ages out of the test.
PERMITS = [
    # regression: the permit that started the objection work stays visible
    _permit("2026/0439.00", "בבדיקה", 'הפלמ"ח 41', pub=_d(-7)),
    # category 1: published inside the six-month window -> visible
    _permit("2020/0001.01", "בבדיקה", "אלפסי 9", pub=_d(-30), end=_d(-16)),
    # category 4: no publication evidence -> visible, marked date-unknown
    _permit("2020/0002.01", "בבדיקה", "בן יהודה 1"),
    # terminal, undated -> hidden by the existing closed rule
    _permit("2020/0003.01", "הבקשה נסגרה", "הרצל 5"),
    # category 2: published before the window -> hidden by default, recoverable
    _permit("2020/0004.01", "בבדיקה", "יפו 12", pub=_d(-200), end=_d(-186)),
    # category 1 edge: future publication start (real case 2026-10-28) -> visible
    _permit("2020/0005.01", "בבדיקה", "קינג ג'ורג' 3", pub=_d(3)),
    # category 3: publication evidenced by status, date unknown -> visible, marked
    _permit("2020/0006.01", "תום תקופת פרסום", "אמציה 2"),
    # category 3 via planned publication end only -> visible, marked
    _permit("2020/0007.01", "בבדיקה", "בצלאל 4", end=_d(10)),
    # category 4: draft-permit stage (where undated rows concentrate) -> visible
    _permit("2020/0008.01", "טיוטת היתר הוכנה", "נרקיסים 6"),
    # malformed scraper date -> degrades to date-unknown, never a bogus date
    _permit("2020/0009.01", "בבדיקה", "שמאי 8", pub="2026-13-45"),
]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("site")
    cwd = pathlib.Path.cwd()
    (tmp / "data").mkdir()
    shutil.copy(
        ROOT / "data" / "council_ginot_hair.geojson", tmp / "data" / "council.geojson"
    )
    (tmp / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": PERMITS}, ensure_ascii=False), encoding="utf-8"
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
def browser():
    engine = evidence.browser_engine()  # SITE_BROWSER: chromium (default) or webkit
    with sync_api.sync_playwright() as p:
        try:
            b = getattr(p, engine).launch()
        except sync_api.Error as exc:  # browser binary missing
            pytest.skip(f"{engine} not installed: {exc}")
        # The analytics beacon (cloudflareinsights.com) is intentionally
        # unreachable in tests: no external network, and WebKit blocks the
        # cross-origin RUM ping from a local origin. Serve an empty script
        # instead (an aborted request still logs "Failed to load resource" as
        # a page error), so the zero-JS-errors assertions keep covering real
        # page errors (#821).
        orig_new_context = b.new_context

        def new_context_no_analytics(**kw):
            ctx = orig_new_context(**kw)
            ctx.route(
                re.compile(r"cloudflareinsights\.com"),
                lambda route: route.fulfill(
                    status=200, content_type="application/javascript", body=""
                ),
            )
            return ctx

        b.new_context = new_context_no_analytics
        yield b
        b.close()


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class _ThreadingServer(socketserver.ThreadingTCPServer):
    # The test server must not serialize connections: browsers open
    # speculative/parallel connections and the page issues an unconditional
    # 8.1 MB permits.html fetch. A single-threaded TCPServer can sit blocked
    # on an idle pre-connected socket (or a slow stream) while the about.html
    # navigation request queues unserved -> 60s wait_for_url timeouts on
    # WebKit (issue #438, run 40165507922). Real hosts (GitHub Pages) are
    # concurrent, so the test double must be too.
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture(scope="module")
def served(site):
    # served over http (not file://) so the client-side rows.html fetch works (#164)
    handler = functools.partial(_Quiet, directory=str(site))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}"


import contextlib


@contextlib.contextmanager
def recorded_page(browser, request):
    """New page inside an evidence-recording context (issue #422).

    Every test keeps its final screenshot (success evidence). Video and
    Playwright trace are heavier: kept on failure, or on success for tests
    marked @pytest.mark.evidence (representative user-repro flows).
    """
    engine = evidence.browser_engine()
    out = evidence.evidence_dir(evidence.artifact_root(), engine, request.node.nodeid)
    out.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(record_video_dir=str(out / "video"))
    ctx.tracing.start(screenshots=True, snapshots=True)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        yield pg, errors
    finally:
        passed = bool(getattr(request.node, "_e2e_passed", False)) and errors == []
        marked = request.node.get_closest_marker("evidence") is not None
        pg.screenshot(path=str(out / "screenshot.png"), full_page=True)
        keep = evidence.keep_heavy_evidence(passed, marked)
        video = pg.video
        if keep:
            ctx.tracing.stop(path=str(out / "trace.zip"))
        else:
            ctx.tracing.stop()
        ctx.close()  # finalizes the video file
        if keep and video:
            shutil.copy(str(video.path()), str(out / "video.webm"))
        shutil.rmtree(str(out / "video"), ignore_errors=True)


@pytest.fixture
def page(browser, served, request):
    with recorded_page(browser, request) as (pg, errors):
        pg.goto(served + "/index.html")
        pg.wait_for_function(
            "window.__rowsLoaded === true || window.__rowsFailed === true"
        )
        # #441: the full list loads on demand; these tests need all rows.
        pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
        pg.wait_for_function(
            "window.__permitsLoaded === true || window.__permitsFailed === true"
        )
        assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
        assert pg.evaluate("window.__permitsLoaded") is True, (
            "permits.html failed to load"
        )
        yield pg
        assert errors == [], f"JavaScript errors on the page: {errors}"


@contextlib.contextmanager
def recorded_mobile_page(browser, request):
    """recorded_page at a phone viewport with touch (issue #428).

    390x844 iPhone-class viewport, is_mobile and has_touch so taps go through
    the touch path. Evidence lands in the same per-test artifact dir, so the
    retained videos of evidence-marked tests are phone-sized.
    """
    engine = evidence.browser_engine()
    out = evidence.evidence_dir(evidence.artifact_root(), engine, request.node.nodeid)
    out.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        record_video_dir=str(out / "video"),
    )
    ctx.tracing.start(screenshots=True, snapshots=True)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        yield pg, errors
    finally:
        passed = bool(getattr(request.node, "_e2e_passed", False)) and errors == []
        marked = request.node.get_closest_marker("evidence") is not None
        pg.screenshot(path=str(out / "screenshot.png"), full_page=True)
        keep = evidence.keep_heavy_evidence(passed, marked)
        video = pg.video
        if keep:
            ctx.tracing.stop(path=str(out / "trace.zip"))
        else:
            ctx.tracing.stop()
        ctx.close()  # finalizes the video file
        if keep and video:
            shutil.copy(str(video.path()), str(out / "video.webm"))
        shutil.rmtree(str(out / "video"), ignore_errors=True)


@pytest.fixture
def mobile_page(browser, served, request):
    with recorded_mobile_page(browser, request) as (pg, errors):
        pg.goto(served + "/index.html")
        pg.wait_for_function(
            "window.__rowsLoaded === true || window.__rowsFailed === true"
        )
        # #441: the full list loads on demand; these tests need all rows.
        pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
        pg.wait_for_function(
            "window.__permitsLoaded === true || window.__permitsFailed === true"
        )
        assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
        assert pg.evaluate("window.__permitsLoaded") is True, (
            "permits.html failed to load"
        )
        yield pg
        assert errors == [], f"JavaScript errors on the page: {errors}"


def visible_plans(pg):
    return pg.locator("#plans tbody tr:not(.filtered-out)").count()


def plan_ids(pg):
    return pg.locator(
        "#plans tbody tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()


def test_default_view_is_active_only_and_capped_at_20(page):
    assert page.locator("#plans tbody tr").count() == 29
    assert visible_plans(page) == 20
    assert (
        page.locator("#fcount").inner_text() == "מציג 20 מתוך 26"
    )  # 3 approved hidden
    assert not page.locator("#fappr").is_checked()
    assert not any(i.startswith("400-") for i in plan_ids(page))


def test_show_all_button_expands_and_collapses(page):
    page.click("#more")
    assert visible_plans(page) == 26
    page.click("#more")
    assert visible_plans(page) == 20


def test_show_approved_checkbox_reveals_approved(page):
    page.check("#fappr")
    page.click("#more")
    assert visible_plans(page) == 29
    assert any(i.startswith("400-") for i in plan_ids(page))


def test_default_sort_is_farthest_deadline_first(page):
    first = plan_ids(page)[0]
    assert first == "200-22"  # latest objection deadline on top


def test_free_text_search(page):
    page.fill("#fq", "300-2")
    assert plan_ids(page) == ["300-2"]
    page.fill("#fq", "zzz-no-such-plan")
    assert visible_plans(page) == 0
    assert page.locator("#fcount").inner_text() == "מציג 0 מתוך 0"


def test_status_dropdown_filters(page):
    page.select_option("#fstatus", label="בדיקה תכנונית")
    assert visible_plans(page) == 4
    assert all(i.startswith("300-") for i in plan_ids(page))


def test_legend_chip_toggles_status_filter(page):
    chip = page.locator(".legend .chip", has_text="בדיקה תכנונית").first
    chip.click()
    assert page.locator("#fstatus").input_value() == "בדיקה תכנונית"
    assert visible_plans(page) == 4
    assert "sel" in chip.get_attribute("class")
    chip.click()  # second click clears
    assert page.locator("#fstatus").input_value() == ""
    assert visible_plans(page) == 20


def test_open_objection_checkbox(page):
    page.check("#fobj")
    page.click("#more")
    assert visible_plans(page) == 22
    assert all(i.startswith("200-") for i in plan_ids(page))


def test_reset_button_restores_defaults(page):
    page.fill("#fq", "300")
    page.check("#fobj")
    page.click("#freset")
    assert page.locator("#fq").input_value() == ""
    assert not page.locator("#fobj").is_checked()
    assert visible_plans(page) == 20


def test_column_sort_toggles_direction(page):
    btn = page.locator("th button[data-sort='num']")
    btn.click()
    asc = plan_ids(page)
    assert asc == sorted(asc) and "sorted-asc" in btn.get_attribute("class")
    btn.click()
    desc = plan_ids(page)
    assert desc == sorted(desc, reverse=True) and "sorted-desc" in btn.get_attribute(
        "class"
    )


def test_dates_render_dd_mm_yy(page):
    cells = page.locator("#plans tbody tr:not(.filtered-out) td span[data-iso]")
    assert cells.count() > 0
    for i in range(cells.count()):
        iso = cells.nth(i).get_attribute("data-iso")
        txt = cells.nth(i).inner_text()
        assert txt == f"{iso[8:10]}.{iso[5:7]}.{iso[2:4]}"
    assert (
        page.locator("#plans tbody tr", has_text="200-1")
        .first.locator("td")
        .nth(3)
        .inner_text()
        == "15.01.26"
    )


def test_plan_numbers_link_to_mavat(page):
    href = page.locator(
        "#plans tbody tr:not(.filtered-out) td:first-child a"
    ).first.get_attribute("href")
    assert href.startswith("https://mavat.iplan.gov.il/")


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


def test_footer_links(page, site):
    hrefs = page.locator("footer a").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    assert "about.html" in hrefs
    assert "https://github.com/reihlinstinct/ginot-hair-plans" in hrefs
    assert any(h.endswith("CONTRIBUTING.md") for h in hrefs)
    # Keyboard activation: a real user path that still exercises the anchor's
    # navigation. WebKit never reached an actionable pointer-click point on the
    # very long permits page (60s timeout even after scroll-into-view).
    link = page.locator("footer a[href='about.html']")
    link.scroll_into_view_if_needed()
    link.focus()
    # Register the navigation waiter BEFORE the keypress: pressing Enter and
    # only then calling wait_for_url races the actual navigation commit and
    # intermittently hangs 60s on WebKit (seen on CI run 40164675351 after
    # three green same-content runs).
    with page.expect_navigation(url="**/about.html", timeout=60000):
        page.keyboard.press("Enter")
    assert page.url.endswith("/about.html")
    assert page.locator("body").inner_text().strip() != ""


def test_page_has_draft_notice_and_feed_link(page):
    assert page.locator("#permits h2").inner_text() == "בקשות היתר"
    assert (
        page.locator(
            "link[rel='alternate'][type='application/atom+xml']"
        ).get_attribute("href")
        == "feed.xml"
    )


def test_footer_with_about_is_at_the_bottom_of_the_page(page):
    footer = page.locator("footer")
    assert footer.locator("a[href='about.html']").count() == 1
    # footer is the last content element before the script, below every section
    last = page.evaluate("document.body.lastElementChild.tagName")
    assert last == "SCRIPT"
    assert (
        page.evaluate("document.querySelector('footer').nextElementSibling.tagName")
        == "SCRIPT"
    )
    fy = footer.bounding_box()["y"]
    for sel in ("#plans", "#permits", "#stats"):
        box = page.locator(sel).bounding_box()
        assert box["y"] < fy, sel
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    assert footer.is_visible()


def test_statistics_collapsed_by_default_and_expandable(page):
    d = page.locator("details#stats")
    assert d.get_attribute("open") is None
    assert not d.locator(".stats").is_visible()
    d.locator("summary").click()
    assert d.locator(".stats").is_visible()
    assert d.locator("h3").count() == 4
    d.locator("summary").click()
    assert not d.locator(".stats").is_visible()


@pytest.mark.evidence
def test_mobile_search_tap_finds_plan(mobile_page):
    """Phone-sized flow: type in the free-text search, one plan stays (issue #428)."""
    mobile_page.tap("#fq")
    mobile_page.fill("#fq", "300-2")
    assert plan_ids(mobile_page) == ["300-2"]
    assert mobile_page.evaluate("document.documentElement.scrollWidth") <= 391, (
        "horizontal scroll appeared on 390px"
    )


@pytest.mark.evidence
def test_mobile_legend_chip_tap_toggles_status(mobile_page):
    """Phone-sized flow: tapping a legend chip toggles the status filter (issue #428)."""
    chip = mobile_page.locator(".legend .chip", has_text="בדיקה תכנונית").first
    chip.tap()
    assert mobile_page.locator("#fstatus").input_value() == "בדיקה תכנונית"
    assert visible_plans(mobile_page) == 4
    assert "sel" in chip.get_attribute("class")
    chip.tap()  # second tap clears
    assert mobile_page.locator("#fstatus").input_value() == ""
    assert visible_plans(mobile_page) == 20


def test_mobile_permit_search_and_status_filter(mobile_page):
    mobile_page.tap("#pfq")
    mobile_page.fill("#pfq", "אלפסי")
    assert (
        mobile_page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
    )
    mobile_page.tap("#pfreset")
    # #521: legend chips are status groups; a raw status goes in the select.
    mobile_page.select_option("#pfstatus", "בבדיקה")
    assert mobile_page.locator("#pfstatus").input_value() == "בבדיקה"
    assert (
        mobile_page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 7
    )


@pytest.mark.parametrize("w,h", [(390, 844), (360, 800)])
def test_mobile_no_horizontal_scroll_and_cards(browser, site, w, h):
    ctx = browser.new_context(
        viewport={"width": w, "height": h}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.goto((site / "index.html").as_uri())
    assert pg.evaluate("document.documentElement.scrollWidth") <= w + 1
    assert (
        pg.evaluate(
            "getComputedStyle(document.querySelector('#plans tbody tr')).display"
        )
        == "block"
    )
    label = pg.evaluate(
        "getComputedStyle(document.querySelector('#plans tbody tr td:nth-child(4)'), '::before').content"
    )
    assert "קליטה" in label
    # the sort controls stay usable as chips
    assert pg.locator("#plans thead th button").first.is_visible()
    ctx.close()


def test_mobile_tap_targets_and_font_size(browser, served):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.goto(served + "/index.html")
    pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
    for sel in ("#fq", "#fstatus", "#freset", "#more"):
        box = pg.locator(sel).bounding_box()
        assert box["height"] >= 43, sel
        assert (
            float(
                pg.evaluate(
                    f"parseFloat(getComputedStyle(document.querySelector('{sel}')).fontSize)"
                )
            )
            >= 16
        )
    ctx.close()


def test_desktop_keeps_the_table_layout(browser, site):
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    pg = ctx.new_page()
    pg.goto((site / "index.html").as_uri())
    assert (
        pg.evaluate("getComputedStyle(document.querySelector('#plans')).display")
        == "table"
    )
    ctx.close()


def test_urgent_row_matches_deadline_window(browser, served, site):
    import re

    html_src = (site / "rows.html").read_text(encoding="utf-8")  # full row set (#164)
    deadlines = re.findall(r"data-obj='([0-9]{4}-[0-9]{2}-[0-9]{2})'", html_src)
    expected = sorted(
        d for d in deadlines if 0 <= (datetime.date.fromisoformat(d) - TODAY).days <= 30
    )
    assert expected, "fixture must include plans inside the urgent window"
    pg = browser.new_page()
    pg.goto(served + "/index.html?today=" + TODAY.isoformat())
    pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
    items = pg.locator("#urgent-list li").all_inner_texts()
    pg.close()
    assert len(items) == len(expected)
    d = expected[0]
    assert f"{d[8:10]}.{d[5:7]}.{d[0:4]}" in items[0]  # nearest deadline first


def test_urgent_row_empties_once_window_passes(browser, site):
    pg = browser.new_page()
    pg.goto(
        (site / "index.html").as_uri()
        + "?today="
        + (TODAY + datetime.timedelta(days=40)).isoformat()
    )
    items = pg.locator("#urgent-list li").all_inner_texts()
    pg.close()
    assert items == ["אין"]


@pytest.mark.parametrize("width", [390, 1280])
def test_statistics_have_visible_tracks_and_fills(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.locator("#stats summary").click()
    track = page.locator("#stats .bt").first.bounding_box()
    fill = page.locator("#stats .bf").first.bounding_box()
    assert track["width"] >= 30 and track["height"] >= 14
    assert fill["width"] > 0 and fill["height"] >= 14
    assert (
        page.locator("#stats .bf").first.evaluate(
            "e => getComputedStyle(e).backgroundColor"
        )
        != "rgba(0, 0, 0, 0)"
    )
    assert page.locator("#stats .bv").first.inner_text().isdigit()


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


def test_mobile_ai_header_hidden_review_links_preserved(browser, served):
    """#244: hide the non-sort chip, not the actual review links."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.goto(served + "/index.html")
    pg.wait_for_function("window.__rowsLoaded === true")
    assert pg.locator("#plans thead th:nth-child(8)").is_hidden()
    assert pg.locator("#plans thead th button").first.is_visible()
    assert pg.locator("#plans tbody tr").first.locator("td:nth-child(8)").is_visible()
    ctx.close()


def _permit(tik, status, sug="היתר", addr="הרצל 5"):
    return {
        "tik_num": tik,
        "mahut": "x",
        "sugbakasha": sug,
        "status": status,
        "status_date": "2026-10-01",
        "gush": 30007,
        "helka": 12,
        "address": addr,
        "publication_start": "",
        "publication_end_planned": "",
    }


@pytest.mark.evidence
def test_legend_options_and_counts_follow_the_live_fragment(browser, tmp_path, request):
    """Regression (#414): the weekly shell and the feed-updated fragment drift
    apart between Tuesdays (legend said (1) while 8 rows carried the status on
    the live site, 2026-10-24). Legend chips, filter options and the closed
    count must derive from the loaded fragment, not the stale shell."""
    from ginot import page as _page

    shell_permits = [_permit("2020/0001.00", "בבדיקה")]
    live_permits = shell_permits + [
        _permit("2026/0439.00", "תחילת פרסום הבקשה להקלה", addr="הפלמח 41 קטמון הישנה"),
        _permit("2026/0439.01", "תחילת פרסום הבקשה להקלה", addr="הפלמח 43 קטמון הישנה"),
        _permit("1990/0002.00", "הבקשה נסגרה"),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(
        json.dumps({"requests": shell_permits}, ensure_ascii=False), encoding="utf-8"
    )
    plan = {
        "pl_number": "1",
        "pl_name": "תכנית 1",
        "station_desc": "הפקדה",
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }
    _page.render_site([plan], [], str(tmp_path), permits_path=str(pf))
    # feed publish re-renders ONLY the fragment from newer data (#412 flow)
    _page._permits_section(live_permits, rows_file=str(tmp_path / "permits.html"))

    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, _errs):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            # #441: the full list loads on demand; these tests need all rows.
            pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
            pg.wait_for_function(
                "window.__permitsLoaded === true || window.__permitsFailed === true"
            )
            assert pg.evaluate("window.__permitsLoaded") is True
            new_status = "תחילת פרסום הבקשה להקלה"
            # dropdown gains the status that only exists in the live fragment
            options = pg.locator("#pfstatus option").all_text_contents()
            assert new_status in options
            # legend chip counts come from the fragment rows, not the shell;
            # chips are status GROUPS since #521 (raw statuses fill the select)
            chips = pg.locator("#permits .legend .chip").all_text_contents()
            assert "פתוח להתנגדויות (2)" in chips
            assert "לא מסווג (1)" in chips
            assert "סגור/אחר (1)" in chips
            # closed count label follows the fragment
            label = pg.locator("#pfilters label", has_text="הצג בקשות שהסתיימו")
            assert "(1)" in label.inner_text()
            # selecting the new status filters to exactly its rows
            pg.select_option("#pfstatus", new_status)
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 2


@pytest.mark.evidence
def test_search_matches_hebrew_punctuation_variants(browser, tmp_path, request):
    """Regression (#413): the user's exact spelling הפלמ״ח (geresh) returned 0
    on the live site 2026-10-24 while the municipal address spells הפלמח
    without geresh. Geresh, gershayim, apostrophes, quotes and maqaf/hyphen
    normalize away on both the query and the indexed row text."""
    from ginot import page as _page

    permits = [
        _permit("2026/0439.00", "תחילת פרסום הבקשה להקלה", addr="הפלמח 41 קטמון הישנה"),
        _permit("2020/0001.00", "בבדיקה", addr="הרצל 5"),
        # #468 row-side folding: pointed letters, a typographic quote, NBSP and
        # an RLM in the stored address must fold like the query does.
        _permit(
            "2020/0002.00",
            "בבדיקה",
            addr="\u200fהַמֶּלֶךְ\u00a0ג\u2018ורג\u2018  60",
        ),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(
        json.dumps({"requests": permits}, ensure_ascii=False), encoding="utf-8"
    )
    plan = {
        "pl_number": "1",
        "pl_name": "תכנית 1",
        "station_desc": "הפקדה",
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }
    _page.render_site([plan], [], str(tmp_path), permits_path=str(pf))
    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, _errs):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            # #441: the full list loads on demand; these tests need all rows.
            pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
            pg.wait_for_function(
                "window.__permitsLoaded === true || window.__permitsFailed === true"
            )
            assert pg.evaluate("window.__permitsLoaded") is True
            # #468: typographic quotes, primes, niqqud, NBSP and doubled
            # spaces fold the same way as the #413 ASCII/Hebrew variants.
            for variant in [
                "הפלמ״ח",
                'הפלמ"ח',
                "הפלמ'ח",
                "הפלמח",
                "הפלמח 41",
                "הפלמ\u201cח",
                "הפלמ\u201dח",
                "הפלמ\u2033ח",
                "הפלמ\u2019ח",
                "\u05d4\u05b7\u05e4\u05bc\u05b8\u05dc\u05de\u05d7",  # pointed
                "הפלמח\u00a041",
                "הפלמח   41",
                "\u200fהפלמח 41",
            ]:
                pg.fill("#pfq", "")
                pg.fill("#pfq", variant)
                pg.dispatch_event("#pfq", "input")
                visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
                texts = visible.all_text_contents()
                assert len(texts) == 1 and "2026/0439.00" in texts[0], (
                    f"{variant!r} should find exactly the הפלמח 41 row, got {texts}"
                )
            for variant in ["המלך גורג 60", "המלך ג'ורג' 60", "ג׳ורג׳"]:
                pg.fill("#pfq", "")
                pg.fill("#pfq", variant)
                pg.dispatch_event("#pfq", "input")
                visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
                texts = visible.all_text_contents()
                assert len(texts) == 1 and "2020/0002.00" in texts[0], (
                    f"{variant!r} should find exactly the pointed-address row, got {texts}"
                )


def _plan_row(num, name, status="הפקדה"):
    return {
        "pl_number": num,
        "pl_name": name,
        "station_desc": status,
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_60d_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": f"https://mavat.iplan.gov.il/{num}",
    }


def test_plan_search_folds_spelling_variants_without_aliases(
    browser, tmp_path, request
):
    """Regression (#468): the owner could not find plan 101-0617134 by a
    spelling variant. The plans table must fold geresh/quote/prime variants,
    niqqud, dashes and whitespace runs identically on query and row text,
    keep literal plan-number matching, and add NO aliases: the plan feed
    carries no street field, so the colloquial "קינג גורג" stays a miss.
    Synthetic rows; the official name shape is decorated with row-side
    Unicode variants to cover query AND index normalization (#678)."""
    from ginot import page as _page

    plans = [
        _plan_row(
            "101-0617134", "מלון\u00a0המלכים\u200f\u2013 הַמֶּלֶך\u00a0ג\u2018ורג\u2018  60"
        ),
        _plan_row("101-0000001", "גולדה מאיר 3"),
        _plan_row("101-0000002", "הרצל 5"),
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(json.dumps({"requests": []}, ensure_ascii=False), encoding="utf-8")
    _page.render_site(plans, [], str(tmp_path), permits_path=str(pf))
    handler = functools.partial(_Quiet, directory=str(tmp_path))
    with _ThreadingServer(("127.0.0.1", 0), handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with recorded_page(browser, request) as (pg, errors):
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
            pg.wait_for_function(
                "window.__rowsLoaded === true || window.__rowsFailed === true"
            )
            assert pg.evaluate("window.__rowsLoaded") is True
            pg.check("#fappr")

            def ids(query):
                pg.fill("#fq", query)
                pg.dispatch_event("#fq", "input")
                return sorted(plan_ids(pg))

            everything = ids("")
            assert len(everything) == 3
            george = ["101-0617134"]
            for variant in [
                "ג'ורג'",
                "ג׳ורג׳",
                "ג\u2019ורג\u2019",
                "ג\u2018ורג\u2018",
                "ג\u2032ורג\u2032",
                "גורג",
                "המלך ג׳ורג׳ 60",
                "המלך  ג'ורג'  60",
                "המלך\u00a0גורג",
                "המלכים - המלך",
                "המלכים \u2013 המלך",
                "\u05d4\u05b7\u05de\u05bc\u05b6\u05dc\u05b6\u05da\u05b0 גורג",
                "\u200fמלון המלכים",
                # literal plan-number matching is preserved
                "101-0617134",
                "1010617134",
                "0617134",
                "101\u20110617134",
            ]:
                assert ids(variant) == george, (
                    f"{variant!r} should find only 101-0617134"
                )
            # no aliases: no committed source spells the plan this way
            assert ids("קינג גורג") == []
            # no false-positive broadening
            assert ids("הרצל") == ["101-0000002"]
            assert ids("גולדה") == ["101-0000001"]
            assert ids("צ") == ["101-0000002"]  # one letter: only rows containing it
            assert ids("ט") == []
            assert ids("'") == everything  # punctuation-only behaves like empty
            assert ids("   ") == everything
            assert errors == [], f"JavaScript errors on the page: {errors}"


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


# --- #441: default subset first, full list lazily -------------------------

_LAZY_OBJ = "תחילת פרסום הבקשה להקלה"
_LAZY_REVIEW = "שולמה מקדמה"


def _lazy_site(tmp_path, evidence=(), dated=False):
    """Synthetic site: 3 open objection rows (in the default subset) and 30
    review-group rows (full list only), one with a unique search word."""
    from ginot.page import render_site

    source = tmp_path / "source"
    source.mkdir()
    requests = [
        {
            "tik_num": f"2026/01{i:02d}.00",
            "status": _LAZY_OBJ,
            "address": f"רחוב אלף {i}",
        }
        for i in range(3)
    ] + [
        {
            "tik_num": f"2026/02{i:02d}.00",
            "status": _LAZY_REVIEW,
            "address": "רחוב ייחודי 7" if i == 29 else f"רחוב בית {i}",
        }
        for i in range(30)
    ]
    if dated:  # open objection windows, so the urgency list is not empty
        today = today_il()
        for i, r in enumerate(requests[:3]):
            r["publication_start"] = (today - datetime.timedelta(days=5)).isoformat()
            r["publication_end_planned"] = (
                today + datetime.timedelta(days=5 + i)
            ).isoformat()
    (source / "permit_requests.json").write_text(
        json.dumps({"requests": requests}, ensure_ascii=False), encoding="utf-8"
    )
    (source / "publications_active.json").write_text(json.dumps(list(evidence)))
    out = tmp_path / "site"
    render_site([], [], str(out), permits_path=str(source / "permit_requests.json"))
    handler = functools.partial(_Quiet, directory=str(out))
    srv = _ThreadingServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


def _count_requests(pg):
    seen = {"permits.html": 0, "permits-default.html": 0}

    def on_request(req):
        name = req.url.rsplit("/", 1)[-1].split("?", 1)[0]
        if name in seen:
            seen[name] += 1

    pg.on("request", on_request)
    return seen


def test_default_load_fetches_only_the_subset(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.wait_for_timeout(300)
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            assert visible.count() == 3
            assert pg.locator("#pfload").inner_text() == ""
            assert errors == []
    finally:
        srv.shutdown()


def test_search_outside_subset_loads_full_list_once(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            # a concurrent burst of triggers shares one request
            pg.evaluate(
                "Promise.all([window.__loadFullPermits(), window.__loadFullPermits()])"
            )
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsLoaded === true")
            # the review group is not selected by default: select it
            # (the chip sits behind the "more statuses" disclosure)
            pg.evaluate(
                """document.querySelector('#pfgroups .chip[data-group="review"]').click()"""
            )
            row = pg.locator('tr[data-tik="2026/0229.00"]')
            row.wait_for(state="visible")
            pg.locator("#pfq").fill("רחוב")
            pg.locator("#pmore").click()
            assert seen == {"permits.html": 1, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_full_list_failure_shows_retry_and_keeps_subset(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            state = {"fail": True}

            def handle(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", handle)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsFailed === true")
            assert pg.locator("#pfretry").is_visible()
            # no counters computed from the subset while the view is incomplete
            assert pg.locator("#pfcount").inner_text() == ""
            assert pg.locator("#pfunknown").inner_text() == ""
            # a non-default view never shows subset results as if complete
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 0
            assert pg.locator("#permits-table tbody tr").count() == 3  # subset kept
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr").count() == 33
            # back to the default view: same 3 rows as the subset showed
            pg.locator("#pfreset").click()
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert seen["permits.html"] == 2
            assert errors == []
    finally:
        srv.shutdown()


def test_evidence_outside_subset_triggers_full_load(tmp_path, browser, request):
    # Evidence for a tik the render did not know: the subset is older than
    # the daily publication list, so the page loads the full list itself.
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsLoaded === true")
            row = pg.locator('tr[data-tik="2026/0205.00"]')
            row.wait_for(state="visible")
            assert row.get_attribute("data-group") == "obj"
            assert seen == {"permits.html": 1, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_default_view_urgency_and_map_rows_match_full_load(tmp_path, browser, request):
    """The map draws the visible permit rows (plan-map.js permitRows) and the
    urgency list scans the obj rows: both must be the same on the subset as
    after the full list loads, in the default view."""
    srv, url = _lazy_site(tmp_path, dated=True)
    visible = (
        "Array.from(document.querySelectorAll('#permits-table tbody tr'))"
        ".filter(r=>!r.classList.contains('filtered-out')).map(r=>r.dataset.tik)"
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            subset_rows = pg.evaluate(visible)
            subset_urgent = pg.locator("#urgent-list").inner_text()
            subset_count = pg.locator("#pfcount").inner_text()
            assert len(subset_rows) == 3
            assert "2026/0100.00" in subset_urgent
            pg.evaluate("window.__loadFullPermits()")
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate(visible) == subset_rows
            assert pg.locator("#urgent-list").inner_text() == subset_urgent
            assert pg.locator("#pfcount").inner_text() == subset_count
            assert errors == []
    finally:
        srv.shutdown()


def test_old_evidence_outside_subset_does_not_load_full_list(
    tmp_path, browser, request
):
    """Evidence outside the overlay window (here: a closed request published
    years ago) promotes nothing, so it must not trigger the 12 MB fetch. On
    the committed data three such entries made every default load fetch it."""
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2019/0001.00",
                    "in_polygon": True,
                    "publication_date": "2019-04-17",
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function(
                "window.__permitsDefaultLoaded === true "
                "&& window.__permitPublicationEvidenceLoaded === true"
            )
            pg.wait_for_timeout(300)
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_new_unmapped_subset_status_is_visible_without_full_fetch(
    tmp_path, browser, request
):
    """#622: a feed fragment can add a group absent from the weekly shell."""
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)

            def new_status(route):
                original = route.fetch().text()
                # Only the fragment changes, not index.html or its chips.
                replacement = original.replace(
                    "data-group='obj'", "data-group='unmapped'"
                )
                route.fulfill(body=replacement, content_type="text/html")

            pg.route("**/permits-default.html", new_status)
            pg.route("**/permits.html", new_status)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            chip = pg.locator('#pfgroups .chip[data-group="unmapped"]')
            assert chip.count() == 1
            assert "sel" in chip.get_attribute("class")
            assert chip.get_attribute("data-default") == "1"
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            assert visible.count() == 3
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            chip.click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator('#pfgroups .chip[data-group="unmapped"]').count() == 1
            pg.locator("#pfreset").click()
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert "sel" in chip.get_attribute("class")
            assert seen["permits.html"] == 1
            assert errors == []
    finally:
        srv.shutdown()


def test_full_install_failure_can_retry_after_table_returns(tmp_path, browser, request):
    """#623: an unavailable target must not latch the shared promise forever."""
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.evaluate("""async () => {
              window.__savedPermitBody=document.querySelector('#permits-table tbody');
              window.__savedPermitBody.remove();
              window.__firstInstallResult=await window.__loadFullPermits();
              document.querySelector('#permits-table').appendChild(window.__savedPermitBody);
            }""")
            assert pg.evaluate("window.__firstInstallResult") is False
            pg.evaluate("window.__loadFullPermits()")
            pg.wait_for_function("window.__permitsLoaded === true", timeout=2000)
            assert seen["permits.html"] == 2
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert errors == []
    finally:
        srv.shutdown()


def test_subset_and_full_failure_offer_retry_in_default_view(
    tmp_path, browser, request
):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            publications = []
            publication_state = {"release": False}

            def publication(route):
                if publication_state["release"]:
                    route.fulfill(content_type="application/json", body="[]")
                else:
                    publications.append(route)

            pg.route("**/publications_active.json", publication)
            pg.route(
                "**/permits-default.html", lambda r: r.fulfill(status=503, body="")
            )
            state = {"fail": True}

            def full(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", full)
            pg.goto(url)
            pg.wait_for_function(
                "window.__permitsDefaultFailed && window.__permitsFailed"
            )
            publication_state["release"] = True
            for route in publications:
                route.fulfill(content_type="application/json", body="[]")
            pg.wait_for_function(
                "window.__permitPublicationEvidenceLoaded && window.__permitOfficialDeadlines"
            )
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            pg.locator("#pfq").fill("ייחודי")
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            pg.locator("#pfreset").click()
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert errors == []
    finally:
        srv.shutdown()


def test_late_publication_overlay_refreshes_urgent_list(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path, dated=True)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pending = []
            count = {"n": 0}
            deadline = (today_il() + datetime.timedelta(days=5)).isoformat()
            evidence = [
                {
                    "tik_num": "2026/0100.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": deadline,
                }
            ]

            def publications(route):
                count["n"] += 1
                if count["n"] == 1:
                    route.fulfill(
                        content_type="application/json", body=json.dumps(evidence)
                    )
                else:
                    pending.append(route)

            def subset(route):
                text = (
                    route.fetch()
                    .text()
                    .replace("data-group='obj'", "data-group='review'")
                )
                route.fulfill(content_type="text/html", body=text)

            pg.route("**/publications_active.json", publications)
            pg.route("**/permits-default.html", subset)
            pg.goto(url, wait_until="domcontentloaded")
            pg.wait_for_function(
                "window.__permitsDefaultLoaded && window.__permitOfficialDeadlines"
            )
            assert "2026/0100.00" not in pg.locator("#urgent-list").inner_text()
            assert len(pending) == 1
            pending[0].fulfill(
                content_type="application/json", body=json.dumps(evidence)
            )
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded")
            assert "2026/0100.00" in pg.locator("#urgent-list").inner_text()
            assert (
                pg.locator('tr[data-tik="2026/0100.00"]').get_attribute("data-group")
                == "obj"
            )
            assert errors == []
    finally:
        srv.shutdown()


def test_failed_evidence_full_load_offers_retry_and_keeps_subset(
    tmp_path, browser, request
):
    """A current publication for a permit missing from the subset makes the
    page fetch the full list from the default view. If that fails, the subset
    stays visible but the page must say so and offer retry, even after a
    later apply() (CodeRabbit 4389333868)."""
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    state = {"fail": True}

    def full(route):
        if state["fail"]:
            route.fulfill(status=503, body="")
        else:
            route.continue_()

    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.route("**/permits.html", full)
            pg.goto(url)
            pg.wait_for_function("window.__permitsFailed === true")
            assert pg.locator("#pfretry").is_visible()
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            subset_tiks = pg.locator("#permits-table tbody tr").evaluate_all(
                '(rows) => rows.map(r => r.getAttribute("data-tik"))'
            )
            assert subset_tiks
            assert visible.count() == len(subset_tiks)  # the subset stays
            pg.locator("#pfreset").click()  # a later apply() keeps the state
            assert pg.locator("#pfretry").is_visible()
            assert visible.count() == len(subset_tiks)
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator("#pfload").inner_text() == ""
            pg.locator('tr[data-tik="2026/0205.00"]').wait_for(state="visible")
            assert errors == []
    finally:
        srv.shutdown()


def test_filter_link_hebrew_and_permit_state_roundtrip(page):
    page.fill("#fq", "תכנית")
    page.check("#fappr")
    page.click('#plans th button[data-sort="num"]')
    page.fill("#pfq", "הפלמח")
    page.wait_for_function("window.__permitsLoaded === true")
    expected_plans = plan_ids(page)
    expected_permits = page.locator(
        "#permits-table tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    link = page.evaluate("window.GinotFilterLinks.build()")
    assert "filters=1" in link
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#fq") == "תכנית"
    assert page.is_checked("#fappr")
    assert page.input_value("#pfq") == "הפלמח"
    assert plan_ids(page) == expected_plans
    assert (
        page.locator(
            "#permits-table tr:not(.filtered-out) td:first-child"
        ).all_inner_texts()
        == expected_permits
    )


def test_filter_link_invalid_values_and_clipboard_fallback(page):
    url = page.url.split("?")[0]
    page.goto(
        url + "?filters=1&plan.fflag=garbage&plan.ffrom=2026-02-30&plan.fappr=no#plans"
    )
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fflag") == ""
    assert page.input_value("#ffrom") == ""
    assert not page.is_checked("#fappr")
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('denied'))},configurable:true})"
    )
    page.click("#copy-plan-link")
    link = page.locator('input[aria-label="קישור לסינון הנוכחי"]:visible')
    assert link.count() == 1
    assert "#plans" in link.input_value()
    assert page.locator('[role="status"]', has_text="לא הועתק").count() == 1


def test_filter_link_copy_success_and_unknown_version(page):
    page.goto(page.url.split("?")[0] + "?filters=99&plan.fq=ignored&today=2026-10-26")
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fq") == ""
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{value:{writeText:t=>{window.__copied=t;return Promise.resolve();}},configurable:true})"
    )
    page.click("#copy-plan-link")
    page.wait_for_function("window.__copied")
    assert "today=2026-10-26" in page.evaluate("window.__copied")
    assert page.locator('[role="status"]', has_text="הקישור הועתק").count() == 1


def test_filter_link_expanded_groups_and_dates(page):
    page.click("#more")
    page.check("#fappr")
    page.click("#more")
    page.check("#pfclosed")
    page.wait_for_function("window.__permitsLoaded")
    page.uncheck("#pfopenonly")
    page.fill("#pffrom", _d(-120))
    expected_groups = page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.getAttribute('data-group')).sort()"
    )
    link = page.evaluate("GinotFilterLinks.build()")
    expected_ids = plan_ids(page)
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#pffrom") == _d(-120)
    assert page.is_checked("#pfclosed")
    assert not page.is_checked("#pfopenonly")
    assert (
        page.locator("#pfgroups .chip.sel").evaluate_all(
            "els=>els.map(e=>e.getAttribute('data-group')).sort()"
        )
        == expected_groups
    )
    assert plan_ids(page) == expected_ids


def test_filter_link_closed_only_selects_terminal_groups(page):
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfclosed=1")
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        assert page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.classList.contains('sel')"
        )
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfclosed=1&permit.groups=obj")
    page.wait_for_function("window.__permitsLoaded")
    assert page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.getAttribute('data-group'))"
    ) == ["obj"]


def test_filter_link_unknown_keys_do_not_load_and_are_preserved(page):
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.unknown=x&plan.note=hello")
    page.wait_for_function("window.__permitsDefaultLoaded")
    assert not any("/permits.html" in url for url in requests)
    link = page.evaluate("GinotFilterLinks.build()")
    assert "permit.unknown=x" in link and "plan.note=hello" in link


def test_filter_link_copy_disabled_while_url_state_pending(page):
    held = []
    page.route("**/permits.html", lambda route: held.append(route))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfq=הפלמח")
    page.wait_for_function("document.getElementById('pfload').textContent.length > 0")
    assert page.is_disabled("#copy-plan-link") and page.is_disabled("#copy-permit-link")
    for _ in range(250):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "full permit request did not arrive within 5 seconds"
    held[0].continue_()
    page.wait_for_function("window.__permitsLoaded")
    assert page.is_enabled("#copy-plan-link") and page.is_enabled("#copy-permit-link")
    assert page.input_value("#pfq") == "הפלמח"


def test_filter_link_closed_with_terminal_chips_off_roundtrips(page):
    page.check("#pfclosed")
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.click()"
        )
    expected = page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.dataset.group).sort()"
    )
    link = page.evaluate("GinotFilterLinks.build()")
    page.goto(link)
    page.wait_for_function("window.__permitsLoaded")
    assert page.is_checked("#pfclosed")
    assert (
        page.locator("#pfgroups .chip.sel").evaluate_all(
            "els=>els.map(e=>e.dataset.group).sort()"
        )
        == expected
    )


def test_filter_link_invalid_groups_uses_checkbox_fallback(page):
    page.goto(
        page.url.split("?")[0] + "?filters=1&permit.pfclosed=1&permit.groups=invalid"
    )
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        assert page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.classList.contains('sel')"
        )


def test_manual_permit_edit_cancels_pending_shared_url_state(page):
    held = []
    page.route("**/permits.html", lambda route: held.append(route))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfq=הפלמח")
    page.fill("#pfq", "הרצל")
    for _ in range(250):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "full permit request did not arrive within 5 seconds"
    held[0].continue_()
    page.wait_for_function("window.__permitsLoaded")
    assert page.input_value("#pfq") == "הרצל"
    assert page.is_enabled("#copy-plan-link")


def test_restored_plan_status_syncs_legend_and_reset(page):
    status = page.locator(".plan-legend .chip").first.get_attribute("data-status")
    from urllib.parse import urlencode

    page.goto(
        page.url.split("?")[0]
        + "?"
        + urlencode({"filters": "1", "plan.fstatus": status})
    )
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fstatus") == status
    assert page.locator(".plan-legend .chip.sel").evaluate_all(
        "els=>els.map(e=>e.dataset.status)"
    ) == [status]
    page.click("#freset")
    assert page.locator(".plan-legend .chip.sel").count() == 0


def test_full_list_render_failure_is_not_a_load_failure(tmp_path, browser, request):
    # #624: the full list fetches and installs fine, but a post-install step
    # throws. The honest state is "loaded, processing failed" with a retry
    # that re-runs the post-install steps only - not a refetch, not the
    # load-failure message.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.evaluate(
                "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
            )
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            # not mislabeled as a load failure
            assert pg.evaluate("window.__permitsFailed") is False
            assert pg.locator("#pfretry").count() == 0
            assert pg.locator("#pfrenderretry").is_visible()
            assert "נטענה" in pg.locator("#pfload").inner_text()
            # the full list is installed: all 33 rows are in the table
            assert pg.locator("#permits-table tbody tr").count() == 33
            # ...but never unfiltered under the active query: the filter was
            # replayed, so some rows carry filtered-out (0 when it was not).
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            # retry re-runs the post-install steps without refetching
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert seen["permits.html"] == 1
            assert errors == []
    finally:
        srv.shutdown()


def test_subset_render_failure_keeps_subset_without_full_reload(
    tmp_path, browser, request
):
    # #624: a post-install failure on the subset path must keep the subset
    # rows, say what failed, and not fall into the fetch-failure catch that
    # would trigger a misleading full reload.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)

            def handle(route):
                resp = route.fetch()
                pg.evaluate(
                    "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
                )
                route.fulfill(response=resp)

            pg.route("**/permits-default.html", handle)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            # not treated as a subset fetch failure: no fallback full reload
            assert pg.evaluate("window.__permitsDefaultFailed") is not True
            assert seen.get("permits.html", 0) == 0
            assert pg.locator("#pfrenderretry").is_visible()
            assert "נטענה" in pg.locator("#pfload").inner_text()
            assert pg.locator("#permits-table tbody tr").count() == 3
            # a later apply cycle must not wipe the render retry in default view
            pg.locator("#pfreset").click()
            assert pg.locator("#pfrenderretry").is_visible()
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert seen.get("permits.html", 0) == 0
            assert errors == []
    finally:
        srv.shutdown()


def test_evidence_loaded_fires_despite_render_failure(tmp_path, browser, request):
    # #751 CodeRabbit: a render exception in the publications callback must not
    # swallow publication-evidence-loaded - the #441 safety net would never
    # notice a newly published permit outside the subset.
    srv, url = _lazy_site(tmp_path)
    # The subset renders before the evidence exists (daily list refreshes
    # independently), so the tik is genuinely outside the subset.
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, _errors):
            seen = _count_requests(pg)
            patch = "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"

            def handle(route):
                resp = route.fetch()
                pg.evaluate(patch)
                route.fulfill(response=resp)

            def handle_pubs(route):
                # publications_active.json may resolve before the subset fetch:
                # install the throwing hook here too, or the publications
                # callback would render fine and the test would pass without
                # exercising the failure path it exists to pin.
                pg.evaluate(patch)
                route.continue_()

            pg.route("**/permits-default.html", handle)
            pg.route("**/publications_active.json", handle_pubs)
            pg.goto(url)
            # the safety net still triggers the full load
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            assert pg.evaluate("window.__permitPublicationEvidenceLoaded") is True
            assert seen["permits.html"] == 1
    finally:
        srv.shutdown()


def test_render_failure_then_full_load_failure_shows_load_retry(
    tmp_path, browser, request
):
    # #751 CodeRabbit: subset render failure + evidence-driven full fetch that
    # also fails must surface the full-load retry (the missing permits cannot
    # be fetched through the render retry).
    srv, url = _lazy_site(tmp_path)
    # The subset renders before the evidence exists (daily list refreshes
    # independently), so the tik is genuinely outside the subset.
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            state = {"fail": True}

            def fail_full(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", fail_full)

            def patch_render(route):
                resp = route.fetch()
                pg.evaluate(
                    "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
                )
                route.fulfill(response=resp)

            pg.route("**/permits-default.html", patch_render)
            pg.goto(url)
            pg.wait_for_function("window.__permitsFailed === true")
            # the full-load retry is visible, not only the render retry
            assert pg.locator("#pfretry").is_visible()
            # recover: unpatch rendering, un-fail the fetch, retry the load
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert errors == []
    finally:
        srv.shutdown()


# #757: wraps the permit filter-link restore so the page-specific extra restore
# (expanded/group state) throws on its first invocation. The standard controls
# (pfq etc.) are set before that throw, so a pre-apply post-install failure
# leaves the restored filter values in place for the catch's replay.
_PATCH_EXTRA_RESTORE_ONCE = """
(function(){
  var real;
  Object.defineProperty(window, 'GinotFilterLinks', {
    configurable: true,
    get: function(){ return real; },
    set: function(v){
      var orig = v.register;
      real = {register: function(name, controls, extra){
        if(name === 'permit' && extra && extra.restore){
          var origExtra = extra.restore, first = true;
          extra = Object.assign({}, extra, {restore: function(p, n){
            if(first){ first = false; throw new Error('synthetic extra-restore failure'); }
            return origExtra(p, n);
          }});
        }
        return orig(name, controls, extra);
      }, build: v.build};
    }
  });
})();
"""


def test_publication_success_restores_stranded_url_state(tmp_path, browser, request):
    # #757: full-load post-install fails before apply() (the permit extra
    # restore throws once), leaving pendingUrlState stranded behind a render
    # retry. A later publications success must complete the deferred restore
    # before clearing the retry - clearing it without the restore hides the
    # only re-run path and leaves the shared-link controls disabled forever.
    # The same test pins the full-load catch's pre-apply filter replay: the
    # restored pfq value filters rows even though runFullPostInstall's own
    # apply() never ran.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script(_PATCH_EXTRA_RESTORE_ONCE)

            def hold_pubs(route):
                # publications_active.json must resolve only after the failed
                # full load surfaced its render retry and the stranded-state
                # assertions below ran (releasing earlier races the cleanup).
                # The release gate is page-side: blocking on a threading
                # primitive here would freeze the sync event loop.
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            # pre-apply replay pin: the restored query filters the installed
            # rows even though runFullPostInstall's apply() never ran.
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            # the retry stays up while the URL state is pending
            assert pg.locator("#copy-permit-link").is_disabled()
            # publications evidence arrives and renders cleanly: the retry is
            # superseded only after the stranded URL state is restored.
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfrenderretry").count() == 0
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


# #757: installs a switchable throwing __renderUrgent wrapper before any page
# script runs. Patching via evaluate() from a route handler races the full
# load: the handler can land after runFullPostInstall already ran (seen in
# CI), and the render failure never happens.
_PATCH_RENDER_URGENT_THROW_SWITCH = """
(function(){
  var real;
  window.__renderShouldThrow = true;
  Object.defineProperty(window, '__renderUrgent', {
    configurable: true,
    get: function(){ return function(){ if(window.__renderShouldThrow) throw new Error('synthetic'); return real && real(); }; },
    set: function(v){ real = v; }
  });
})();
"""


def test_publication_success_supersedes_render_failure_with_url_state(
    tmp_path, browser, request
):
    # #757: intended-behavior pin - with a shared-link filter active, a
    # post-apply render failure (throwing __renderUrgent, after the URL state
    # was already restored) is cleared by a later successful publications
    # re-render, and the restored filter stays in effect.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script(_PATCH_RENDER_URGENT_THROW_SWITCH)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                # Same page-side release gate as the stranded-state test:
                # continuing right after the flag flips races the assertions.
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.input_value("#pfq") == "ייחודי"
            pg.evaluate(
                "window.__renderShouldThrow = false; window.__releasePubs = true"
            )
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfrenderretry").count() == 0
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


def test_early_publications_do_not_consume_pending_url_state(
    tmp_path, browser, request
):
    # #757 (CodeRabbit): a publications response that lands before the full
    # permits load must not consume the pending URL-state restore: group chips
    # introduced only by the full rows (ensureGroupChips, #622) fail validation
    # against the subset, silently dropping the link's group selection.
    srv, url = _lazy_site(tmp_path)
    # One full-list-only row carries a status no group maps (#521: unmapped is
    # fail-visible). Its chip exists only after ensureGroupChips runs on the
    # full rows.
    frag = tmp_path / "site" / "permits.html"
    html = frag.read_text()
    old = "data-group='review' data-scope="
    assert html.count(old) >= 1
    frag.write_text(
        html.replace(
            "data-status='שולמה מקדמה'", "data-status='סטטוס חדש לגמרי'", 1
        ).replace(old, "data-group='unmapped' data-scope=", 1)
    )
    try:
        with recorded_page(browser, request) as (pg, errors):

            def hold_full(route):
                # publications resolve while the full load is still in flight
                pg.wait_for_function(
                    "window.__permitPublicationEvidenceLoaded === true"
                )
                route.continue_()

            pg.route("**/permits.html", hold_full)
            pg.goto(url + "?filters=1&permit.groups=unmapped")
            pg.wait_for_function("window.__permitsLoaded === true")
            # the deferred restore ran against the full rows: the unmapped
            # chip was added by ensureGroupChips, then selected by the link.
            assert pg.locator(".chip[data-group='unmapped'].sel").count() == 1
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert errors == []
    finally:
        srv.shutdown()


# #759: makes permit-link restore() throw for the first window.__restoreThrowsLeft
# invocations (the page scripts live in an IIFE, so restore itself - reached
# through the GinotFilterLinks registrar, an assignment the init script can
# intercept - is the only fault point ahead of apply()). Each test arms the
# count with its own init script before this one.
_PATCH_PERMIT_RESTORE_THROW_N = """
(function(){
  var real;
  Object.defineProperty(window, 'GinotFilterLinks', {
    configurable: true,
    get: function(){ return real; },
    set: function(v){
      var orig = v.register;
      real = {register: function(name, controls, extra){
        var link = orig(name, controls, extra);
        if(name === 'permit' && link && link.restore){
          var origRestore = link.restore;
          link.restore = function(p, n){
            if(window.__restoreThrowsLeft > 0){
              window.__restoreThrowsLeft--;
              throw new Error('synthetic restore failure');
            }
            return origRestore(p, n);
          };
        }
        return link;
      }, build: v.build};
    }
  });
})();
"""


def test_publication_retry_rerun_restores_pending_url_state(tmp_path, browser, request):
    # #759: pins the restore line inside the publications catch retry-rerun.
    # restore() throws twice: the post-install attempt (stranding the pending
    # URL state behind a render retry) and the first publications success
    # render (its catch shows the retry bound to the publications rerun). The
    # pending state must survive both failures - controls stay disabled -
    # and clicking the retry must run the rerun's own restore.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script("window.__restoreThrowsLeft = 2")
            pg.add_init_script(_PATCH_PERMIT_RESTORE_THROW_N)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.locator("#copy-permit-link").is_disabled()
            # publications evidence arrives; its render fails on the restore,
            # which must leave the state pending: retry stays up, controls
            # stay disabled.
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded === true")
            pg.wait_for_function("window.__restoreThrowsLeft === 0")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.locator("#copy-permit-link").is_disabled()
            # the retry rerun is the publications callback: it must restore.
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


# #759: observes the table and the filter control at the __renderUrgent hook,
# which the publications success path calls immediately after apply().
_OBSERVE_AT_RENDER_URGENT = """
window.__renderUrgent = function(){
  window.__pfqAtRenderUrgent = document.getElementById('pfq').value;
  window.__rowsVisibleAtRenderUrgent =
    document.querySelectorAll('#permits-table tbody tr:not(.filtered-out)').length;
};
"""


def test_publication_restore_runs_before_apply(tmp_path, browser, request):
    # #759: pins the restore-before-apply() ordering in the publications
    # success path: the restored controls must filter the render that apply()
    # produces. restore() throws once (post-install), so the controls stay
    # unset until the publications restore; at the post-apply __renderUrgent
    # hook the restored query must already be filtering rows. Were restore
    # moved after apply(), apply() would render with empty controls and the
    # hook would observe an unfiltered table.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script("window.__restoreThrowsLeft = 1")
            pg.add_init_script(_PATCH_PERMIT_RESTORE_THROW_N)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.groups=review&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            pg.evaluate(_OBSERVE_AT_RENDER_URGENT)
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded === true")
            assert pg.evaluate("window.__pfqAtRenderUrgent") == "ייחודי"
            # exactly the one review-group row matching the restored query is
            # visible; an apply() before the restore (default chips, empty
            # query) would have left the 3 default objection rows visible
            assert pg.evaluate("window.__rowsVisibleAtRenderUrgent") == 1
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert errors == []
    finally:
        srv.shutdown()


def test_implicit_or_queries_roundtrip_without_new_controls(page):
    page.fill("#fq", "200-1 | 300-1")
    expected_plans = plan_ids(page)
    assert "200-1" in expected_plans and "300-1" in expected_plans
    page.fill("#pfq", "פלמח 41 | אלפסי 9")
    page.wait_for_function("window.__permitsLoaded === true")
    page.fill("#pffrom", "")
    page.uncheck("#pfopenonly")
    expected = page.locator(
        "#permits-table tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    assert "2026/0439.00" in expected and "2020/0001.01" in expected
    assert page.locator("#fq").count() == page.locator("#pfq").count() == 1
    link = page.evaluate("window.GinotFilterLinks.build()")
    assert "%7C" in link
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#fq") == "200-1 | 300-1"
    assert page.input_value("#pfq") == "פלמח 41 | אלפסי 9"
    assert plan_ids(page) == expected_plans
    assert (
        page.locator(
            "#permits-table tr:not(.filtered-out) td:first-child"
        ).all_inner_texts()
        == expected
    )
