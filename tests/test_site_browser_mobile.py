"""Browser coverage: mobile. Shared fixtures stay in test_site_browser."""

import datetime

import pytest
from test_site_browser import TODAY, plan_ids, visible_plans

pytest_plugins = ["test_site_browser"]


# Section: Mobile


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
