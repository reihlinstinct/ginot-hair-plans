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

PERMITS = [
    {
        "tik_num": "2020/0001.01",
        "status": "בבדיקה",
        "mahut": "תוספת בניה",
        "sugbakasha": "היתר",
        "gush": 30000,
        "helka": 12,
        "address": "אלפסי 9",
        "status_date": "2026-09-01",
        "publication_start": "2026-09-05",
        "publication_end_planned": "2026-09-19",
    },
    {
        "tik_num": "2020/0002.01",
        "status": "בבדיקה",
        "mahut": "שימוש חורג",
        "sugbakasha": "היתר",
        "gush": 30000,
        "helka": 13,
        "address": "בן יהודה 1",
        "status_date": "2026-09-02",
        "publication_start": "",
        "publication_end_planned": "",
    },
    {
        "tik_num": "2020/0003.01",
        "status": "הבקשה נסגרה",
        "mahut": "סגורה",
        "sugbakasha": "היתר",
        "gush": 30000,
        "helka": 14,
        "address": "הרצל 5",
        "status_date": "2026-08-01",
        "publication_start": "",
        "publication_end_planned": "",
    },
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


@pytest.fixture(scope="module")
def served(site):
    # served over http (not file://) so the client-side rows.html fetch works (#164)
    handler = functools.partial(_Quiet, directory=str(site))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as srv:
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


import pytest

@pytest.mark.parametrize("i", range(12))
def test_webkit_race_repro(page, site, i):
    link = page.locator("footer a[href='about.html']")
    link.scroll_into_view_if_needed()
    link.focus()
    page.keyboard.press("Enter")
    try:
        page.wait_for_url("**/about.html", timeout=8000)
    except Exception:
        print(f"REPRO iter={i} WAIT-FAILED final_url={page.url}")
        raise
