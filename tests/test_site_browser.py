"""Headless-browser tests of the built site (issue #106).

The site is built by the real pipeline (refresh.py) from a fixed synthetic
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
import refresh

TODAY = datetime.date.today()
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
    _permit("2026/0439.00", "בבדיקה", "הפלמ\"ח 41", pub=_d(-7)),
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
            "refresh.py",
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
    out = evidence.evidence_dir(
        evidence.artifact_root(), engine, request.node.nodeid
    )
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
        pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
        pg.wait_for_function(
            "window.__permitsLoaded === true || window.__permitsFailed === true"
        )
        assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
        assert pg.evaluate("window.__permitsLoaded") is True, "permits.html failed to load"
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
    out = evidence.evidence_dir(
        evidence.artifact_root(), engine, request.node.nodeid
    )
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
        pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
        pg.wait_for_function(
            "window.__permitsLoaded === true || window.__permitsFailed === true"
        )
        assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
        assert pg.evaluate("window.__permitsLoaded") is True, "permits.html failed to load"
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
    # feed order inside each group. Since #521 there is no recency cutoff, so
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
    assert (
        mobile_page.evaluate("document.documentElement.scrollWidth") <= 391
    ), "horizontal scroll appeared on 390px"


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
        page.locator("#permits .legend .chip[data-group='closed']").get_attribute("class")
    )
    assert page.locator('#permits-table tbody tr[data-active="0"]:visible').count() == 1
    assert page.locator("#fstatus").input_value() == ""
    assert plan_ids(page) == before
    page.click("#pfreset")
    assert "sel" not in (
        page.locator("#permits .legend .chip[data-group='closed']").get_attribute("class")
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
    ]
    pf = tmp_path / "permits.json"
    pf.write_text(json.dumps({"requests": permits}, ensure_ascii=False), encoding="utf-8")
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
            pg.wait_for_function(
                "window.__permitsLoaded === true || window.__permitsFailed === true"
            )
            assert pg.evaluate("window.__permitsLoaded") is True
            for variant in ['הפלמ״ח', 'הפלמ"ח', "הפלמ'ח", "הפלמח", "הפלמח 41"]:
                pg.fill("#pfq", "")
                pg.fill("#pfq", variant)
                pg.dispatch_event("#pfq", "input")
                visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
                texts = visible.all_text_contents()
                assert len(texts) == 1 and "2026/0439.00" in texts[0], (
                    f"{variant!r} should find exactly the הפלמח 41 row, got {texts}"
                )


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
            "refresh.py",
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
