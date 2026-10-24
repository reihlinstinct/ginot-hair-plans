"""Live-site smoke checks against the real network (issue #429).

The browser suites stub all external map traffic (tiles aborted, ArcGIS
fabricated), so a green CI run cannot prove the production map actually
loads — user feedback 24.10: "נראה שהמפה לא נטענה". These checks hit the
production GitHub Pages site with real network and assert the map opens,
Leaflet initialises and real boundaries render, at a phone viewport.

Skipped unless GINOT_LIVE_SMOKE=1 (external services, not PR-blocking):

    GINOT_LIVE_SMOKE=1 SITE_BROWSER=chromium python3 -m pytest tests/test_live_smoke.py -q
    GINOT_LIVE_SMOKE=1 SITE_BROWSER=webkit python3 -m pytest tests/test_live_smoke.py -q
"""

import os

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

LIVE = "https://reihlinstinct.github.io/ginot-hair-plans/"

pytestmark = pytest.mark.skipif(
    os.environ.get("GINOT_LIVE_SMOKE") != "1",
    reason="live smoke: set GINOT_LIVE_SMOKE=1 to run against the production site",
)


@pytest.fixture(scope="module")
def browser():
    engine = os.environ.get("SITE_BROWSER", "chromium")
    with sync_api.sync_playwright() as p:
        try:
            b = getattr(p, engine).launch()
        except sync_api.Error as exc:
            pytest.skip(f"{engine} not installed: {exc}")
        yield b
        b.close()


def test_live_site_loads_rows(browser):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.goto(LIVE)
    pg.wait_for_function(
        "window.__rowsLoaded === true || window.__rowsFailed === true", timeout=30000
    )
    assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
    assert pg.locator("#plans tbody tr").count() > 0
    ctx.close()


def test_live_map_draws_real_boundaries(browser):
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.goto(LIVE)
    pg.wait_for_function(
        "window.__rowsLoaded === true || window.__rowsFailed === true", timeout=30000
    )
    pg.locator("#plan-map-panel summary").click()
    pg.wait_for_selector(".leaflet-container", timeout=30000)
    pg.wait_for_function(
        "document.querySelectorAll('.leaflet-overlay-pane path').length > 0",
        timeout=90000,
    )
    status = pg.locator("#map-status").inner_text()
    import re

    assert re.search(r"[1-9]\d* גבולות", status), f"no boundaries reported: {status}"
    assert pg.locator(".leaflet-tile").count() > 0, "no OSM tiles rendered"
    ctx.close()
