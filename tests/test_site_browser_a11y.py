"""Accessibility regression tests: axe-core scans of the built site.

The site must meet Israeli Standard 5568 (WCAG 2.1 level AA) as a standing
standard (owner decision 2026-11-11). A vendored axe-core build
(tests/fixtures/axe/axe.min.js, pinned below by sha256) is injected into the
real built pages served by the shared site fixtures, and every scanned page
must show zero WCAG 2.0+2.1 A/AA violations of any impact. Keyboard tests pin
the filter chips' button semantics so the legend stays operable without a
mouse.

Skipped when Playwright or its browser is not installed (the CI
"site-browser" job installs both).
"""

import hashlib
import json

import pytest

from test_site_browser import ROOT

pytest_plugins = ["test_site_browser"]

from ginot import i18n  # noqa: E402  (sys.path set up by test_site_browser)

# Section: Vendored axe-core fixture

AXE_PATH = ROOT / "tests" / "fixtures" / "axe" / "axe.min.js"
# axe-core 4.10.3 from https://cdn.jsdelivr.net/npm/axe-core@4.10.3/axe.min.js
AXE_SHA256 = "880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb"

AXE_OPTIONS = {
    "runOnly": {
        "type": "tag",
        # WCAG 2.0 + 2.1 A/AA (SI 5568 adopts WCAG 2.1). No impact filter:
        # every violation, 'minor' included, fails the scan.
        "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
    }
}


def test_axe_fixture_is_the_pinned_build():
    digest = hashlib.sha256(AXE_PATH.read_bytes()).hexdigest()
    assert digest == AXE_SHA256, (
        "tests/fixtures/axe/axe.min.js changed; pin the new build's sha256 here"
    )


def test_axe_scan_options_cover_wcag21_without_an_impact_filter():
    values = AXE_OPTIONS["runOnly"]["values"]
    assert {"wcag2a", "wcag2aa", "wcag21a", "wcag21aa"} <= set(values)
    assert "impact" not in json.dumps(AXE_OPTIONS)


def _axe_violations(pg):
    pg.add_script_tag(path=str(AXE_PATH))
    return pg.evaluate("async (opts) => await axe.run(opts)", AXE_OPTIONS)[
        "violations"
    ]


def _format(violations):
    out = []
    for v in violations:
        targets = ["  " + ", ".join(n["target"]) for n in v["nodes"][:5]]
        out.append(f"{v['id']} ({v['impact']}): {v['help']}\n" + "\n".join(targets))
    return "\n".join(out)


# Section: axe scans of the built pages


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_axe_index_page(browser, served, code):
    pg = browser.new_page()
    pg.goto(served + "/" + i18n.page_path(code, "index.html"))
    pg.wait_for_function("window.__rowsLoaded === true || window.__rowsFailed === true")
    # An empty table is a silent pass, not coverage: the scan requires the
    # real fragments (same contract as the shared page fixture).
    assert pg.evaluate("window.__rowsLoaded") is True, "rows.html failed to load"
    pg.evaluate("window.__loadFullPermits && window.__loadFullPermits()")
    pg.wait_for_function(
        "window.__permitsLoaded === true || window.__permitsFailed === true"
    )
    assert pg.evaluate("window.__permitsLoaded") is True, (
        "permits.html failed to load"
    )
    assert pg.locator("#plans tbody tr").count() > 0
    assert pg.locator("#permits-table tbody tr").count() > 0
    violations = _axe_violations(pg)
    pg.close()
    assert violations == [], f"index [{code}]:\n{_format(violations)}"


@pytest.mark.parametrize("code", i18n.lang_codes())
@pytest.mark.parametrize("name", ["about.html", "email.html", "accessibility.html"])
def test_axe_secondary_pages(browser, served, code, name):
    pg = browser.new_page()
    pg.goto(served + "/" + i18n.page_path(code, name))
    violations = _axe_violations(pg)
    pg.close()
    assert violations == [], f"{name} [{code}]:\n{_format(violations)}"


# Section: keyboard operability of the filter chips


def test_plan_legend_chips_are_keyboard_operable_buttons(page):
    chip = page.locator(".plan-legend .chip").first
    assert chip.evaluate("e => e.tagName") == "BUTTON"
    assert chip.get_attribute("aria-pressed") == "false"
    chip.focus()
    page.keyboard.press("Enter")
    assert chip.get_attribute("aria-pressed") == "true"
    assert chip.get_attribute("class").find("sel") != -1
    page.keyboard.press(" ")
    assert chip.get_attribute("aria-pressed") == "false"


def test_permit_group_chips_are_keyboard_operable_buttons(page):
    chip = page.locator("#pfgroups .chip").first
    assert chip.evaluate("e => e.tagName") == "BUTTON"
    assert chip.get_attribute("aria-pressed") == "true"
    chip.focus()
    page.keyboard.press("Enter")
    assert chip.get_attribute("aria-pressed") == "false"
    page.keyboard.press("Enter")
    assert chip.get_attribute("aria-pressed") == "true"


# Section: the accessibility statement is linked from every page footer


@pytest.mark.parametrize("code", i18n.lang_codes())
@pytest.mark.parametrize("name", ["index.html", "about.html", "email.html"])
def test_footer_links_accessibility_statement(browser, served, code, name):
    pg = browser.new_page()
    pg.goto(served + "/" + i18n.page_path(code, name))
    links = pg.locator('footer a[href$="accessibility.html"]')
    assert links.count() == 1
    pg.close()


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_accessibility_statement_renders(browser, served, code):
    pg = browser.new_page()
    pg.goto(served + "/" + i18n.page_path(code, "accessibility.html"))
    assert pg.locator("h1").count() == 1
    assert "5568" in pg.locator("body").inner_text()
    pg.close()
