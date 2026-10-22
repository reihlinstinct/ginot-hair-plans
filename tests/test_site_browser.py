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

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import refresh

TODAY = datetime.date.today()
MS_DAY = 86400 * 1000


def ms(d):
    return int(datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def feat(num, status, advertise=None, name=None):
    a = {"pl_number": num, "pl_name": name or f"תכנית {num}", "station_desc": status,
         "receiving_date": ms(datetime.date(2026, 1, 15)), "pl_area_dunam": 2.5,
         "pl_url": f"https://mavat.iplan.gov.il/{num}"}
    if advertise:
        a["pl_date_advertise"] = ms(advertise)
    return {"attributes": a, "geometry": None}


# 22 deposit plans (open objection windows, deadlines spread over the next
# 22 days), 4 under review, 3 approved (hidden by default) = 29 plans,
# 26 of them active.
DEPOSIT = [feat(f"200-{i}", "הפקדה להתנגדויות", TODAY + datetime.timedelta(days=i - 50))
           for i in range(1, 23)]
REVIEW = [feat(f"300-{i}", "בדיקה תכנונית") for i in range(1, 5)]
APPROVED = [feat(f"400-{i}", "אישור") for i in range(1, 4)]
FEATURES = DEPOSIT + REVIEW + APPROVED

PERMITS = [
    {"tik_num": "2020/0001.01", "status": "בבדיקה", "mahut": "תוספת בניה", "sugbakasha": "היתר",
     "gush": 30000, "helka": 12, "address": "אלפסי 9", "status_date": "2026-09-01",
     "publication_start": "2026-09-05", "publication_end_planned": "2026-09-19"},
    {"tik_num": "2020/0002.01", "status": "בבדיקה", "mahut": "שימוש חורג", "sugbakasha": "היתר",
     "gush": 30000, "helka": 13, "address": "בן יהודה 1", "status_date": "2026-09-02",
     "publication_start": "", "publication_end_planned": ""},
    {"tik_num": "2020/0003.01", "status": "הבקשה נסגרה", "mahut": "סגורה", "sugbakasha": "היתר",
     "gush": 30000, "helka": 14, "address": "הרצל 5", "status_date": "2026-08-01",
     "publication_start": "", "publication_end_planned": ""},
]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("site")
    cwd = pathlib.Path.cwd()
    (tmp / "data").mkdir()
    shutil.copy(ROOT / "data" / "council_ginot_hair.geojson", tmp / "data" / "council.geojson")
    (tmp / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": PERMITS}, ensure_ascii=False), encoding="utf-8")
    shutil.copytree(ROOT / "docs", tmp / "docs", ignore=shutil.ignore_patterns("badge"))
    mp = pytest.MonkeyPatch()
    mp.chdir(tmp)
    mp.setattr(refresh.iplan, "query_plans",
               lambda council, service="x", **kw: FEATURES if service == "xplan_without_77_78" else [])
    mp.setattr(sys, "argv", ["refresh.py", "--council", "data/council.geojson", "--out", "out",
                             "--site", "docs", "--snapshots", "snapshots", "--status", "data/plan_status.json"])
    refresh.main()
    mp.undo()
    assert pathlib.Path.cwd() == cwd
    return tmp / "docs"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as exc:  # browser binary missing
            pytest.skip(f"chromium not installed: {exc}")
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


@pytest.fixture
def page(browser, served):
    pg = browser.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(served + "/index.html")
    pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
    pg.wait_for_function("window.__permitsLoaded === true || window.__permitsFailed === true")
    assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
    assert pg.evaluate("window.__permitsLoaded") is True, "permits.html failed to load"
    yield pg
    assert errors == [], f"JavaScript errors on the page: {errors}"
    pg.close()


def visible_plans(pg):
    return pg.locator("#plans tbody tr:not(.filtered-out)").count()


def plan_ids(pg):
    return pg.locator("#plans tbody tr:not(.filtered-out) td:first-child").all_inner_texts()


def test_default_view_is_active_only_and_capped_at_20(page):
    assert page.locator("#plans tbody tr").count() == 29
    assert visible_plans(page) == 20
    assert page.locator("#fcount").inner_text() == "מציג 20 מתוך 26"  # 3 approved hidden
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
    assert desc == sorted(desc, reverse=True) and "sorted-desc" in btn.get_attribute("class")


def test_dates_render_dd_mm_yy(page):
    cells = page.locator("#plans tbody tr:not(.filtered-out) td span[data-iso]")
    assert cells.count() > 0
    for i in range(cells.count()):
        iso = cells.nth(i).get_attribute("data-iso")
        txt = cells.nth(i).inner_text()
        assert txt == f"{iso[8:10]}.{iso[5:7]}.{iso[2:4]}"
    assert page.locator("#plans tbody tr", has_text="200-1").first.locator("td").nth(3).inner_text() == "15.01.26"


def test_plan_numbers_link_to_mavat(page):
    href = page.locator("#plans tbody tr:not(.filtered-out) td:first-child a").first.get_attribute("href")
    assert href.startswith("https://mavat.iplan.gov.il/")


def test_permits_default_hides_closed_and_counts(page):
    assert page.locator("#permits-table tbody tr").count() == 3
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 2
    assert page.locator("#pfcount").inner_text() == "מציג 2 מתוך 2"
    page.check("#pfclosed")
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3


def test_permit_search_and_status_chip(page):
    page.fill("#pfq", "אלפסי")
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
    page.click("#pfreset")
    page.locator("#permits .legend .chip", has_text="בבדיקה").click()
    assert page.locator("#pfstatus").input_value() == "בבדיקה"
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 2


def test_permit_publication_date_filter(page):
    page.fill("#pffrom", "2026-09-01")
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
    assert page.locator("#permits-table tbody tr:not(.filtered-out)").inner_text().count("2020/0001.01") == 1


def test_permit_deep_links_point_to_municipality_file(page):
    links = page.locator("#permits-table tbody tr td:first-child a")
    assert links.count() == 3
    href = links.first.get_attribute("href")
    assert href == ("https://ykpubdata.jerusalem.muni.il/#/Details?TikNum=2020%2F0001.01"
                    "&SystemCode=26400046&Page=BakashalInfo")
    assert links.first.get_attribute("target") == "_blank"
    assert "noopener" in links.first.get_attribute("rel")


def test_footer_links(page, site):
    hrefs = page.locator("footer a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert "about.html" in hrefs
    assert "https://github.com/reihlinstinct/ginot-hair-plans" in hrefs
    assert any(h.endswith("CONTRIBUTING.md") for h in hrefs)
    page.click("footer a[href='about.html']")
    assert page.url.endswith("/about.html")
    assert page.locator("body").inner_text().strip() != ""


def test_page_has_draft_notice_and_feed_link(page):
    assert "DRAFT" in page.locator("#permits h2").inner_text()
    assert page.locator("link[rel='alternate'][type='application/atom+xml']").get_attribute("href") == "feed.xml"


def test_footer_with_about_is_at_the_bottom_of_the_page(page):
    footer = page.locator("footer")
    assert footer.locator("a[href='about.html']").count() == 1
    # footer is the last content element before the script, below every section
    last = page.evaluate("document.body.lastElementChild.tagName")
    assert last == "SCRIPT"
    assert page.evaluate("document.querySelector('footer').nextElementSibling.tagName") == "SCRIPT"
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


@pytest.mark.parametrize("w,h", [(390, 844), (360, 800)])
def test_mobile_no_horizontal_scroll_and_cards(browser, site, w, h):
    ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto((site / "index.html").as_uri())
    assert pg.evaluate("document.documentElement.scrollWidth") <= w + 1
    assert pg.evaluate("getComputedStyle(document.querySelector('#plans tbody tr')).display") == "block"
    label = pg.evaluate(
        "getComputedStyle(document.querySelector('#plans tbody tr td:nth-child(4)'), '::before').content")
    assert "קליטה" in label
    # the sort controls stay usable as chips
    assert pg.locator("#plans thead th button").first.is_visible()
    ctx.close()


def test_mobile_tap_targets_and_font_size(browser, served):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(served + "/index.html")
    pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
    for sel in ("#fq", "#fstatus", "#freset", "#more"):
        box = pg.locator(sel).bounding_box()
        assert box["height"] >= 43, sel
        assert float(pg.evaluate(f"parseFloat(getComputedStyle(document.querySelector('{sel}')).fontSize)")) >= 16
    ctx.close()


def test_desktop_keeps_the_table_layout(browser, site):
    ctx = browser.new_context(viewport={"width": 1200, "height": 800})
    pg = ctx.new_page()
    pg.goto((site / "index.html").as_uri())
    assert pg.evaluate("getComputedStyle(document.querySelector('#plans')).display") == "table"
    ctx.close()


def test_urgent_row_matches_deadline_window(browser, served, site):
    import re
    html_src = (site / "rows.html").read_text(encoding="utf-8")  # full row set (#164)
    deadlines = re.findall(r"data-obj='([0-9]{4}-[0-9]{2}-[0-9]{2})'", html_src)
    expected = sorted(d for d in deadlines
                      if 0 <= (datetime.date.fromisoformat(d) - TODAY).days <= 30)
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
    pg.goto((site / "index.html").as_uri() + "?today=" +
            (TODAY + datetime.timedelta(days=40)).isoformat())
    items = pg.locator("#urgent-list li").all_inner_texts()
    pg.close()
    assert items == ["אין"]


def test_map_lazy_filter_legend_and_live_boundary(page):
    page.route("**/plan-points.json", lambda route: route.fulfill(
        json={"generated": "2026-10-22", "points": [
            {"pl_number": "200-1", "pl_name": "Synthetic plan", "station_desc": "הפקדה להתנגדויות",
             "representative_point": [35.213, 31.768]},
            {"pl_number": "200-2", "pl_name": "Other plan", "station_desc": "הפקדה להתנגדויות",
             "representative_point": [35.214, 31.769]}]}))
    page.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
    page.route("https://ags.iplan.gov.il/**", lambda route: route.fulfill(
        json={"type": "FeatureCollection", "features": [{"type": "Feature",
              "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
                  [[35.212, 31.767], [35.214, 31.767], [35.214, 31.769],
                   [35.212, 31.769], [35.212, 31.767]]]}}]}))
    assert page.locator(".leaflet-marker-icon").count() == 0
    page.locator("#plan-map-panel summary").click()
    page.wait_for_selector(".leaflet-marker-icon")
    assert page.locator("#map-legend").is_hidden()
    page.locator("#map-legend-toggle").click()
    assert page.locator("#map-legend").is_visible()
    page.locator("#map-legend-toggle").click()
    page.locator("#fq").fill("200-1")
    page.wait_for_function("document.querySelectorAll('.leaflet-marker-icon').length===1")
    page.locator(".leaflet-marker-icon").click()
    page.get_by_role("button", name="טען גבול תכנית", exact=True).click()
    page.wait_for_function("document.querySelector('#map-status').textContent.includes('נטען כעת')")
    assert page.locator(".leaflet-overlay-pane path").count() == 1
    page.locator("#fq").fill("does-not-exist")
    assert page.locator(".leaflet-marker-icon").count() == 0
    assert "אין תכניות" in page.locator("#map-status").inner_text()
    assert page.locator(".leaflet-overlay-pane path").count() == 0


@pytest.mark.parametrize("width", [390, 1280])
def test_statistics_have_visible_tracks_and_fills(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.locator("#stats summary").click()
    track = page.locator("#stats .bt").first.bounding_box()
    fill = page.locator("#stats .bf").first.bounding_box()
    assert track["width"] >= 30 and track["height"] >= 14
    assert fill["width"] > 0 and fill["height"] >= 14
    assert page.locator("#stats .bf").first.evaluate(
        "e => getComputedStyle(e).backgroundColor") != "rgba(0, 0, 0, 0)"
    assert page.locator("#stats .bv").first.inner_text().isdigit()
