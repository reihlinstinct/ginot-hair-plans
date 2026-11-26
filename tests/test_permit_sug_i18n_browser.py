"""Browser coverage: the permit type select and column on translated pages.

The full permit list rebuilds the type select from the raw Hebrew values at
load. Option text must be the translated type while the option value (and
each row's data-sug) stay the raw Hebrew value that filtering uses.
"""

import functools
import http.server
import pathlib
import threading

import pytest

from ginot import i18n

# Skip the whole module without Playwright, like the other browser files.
pytest.importorskip("playwright.sync_api")

pytest_plugins = ["test_site_browser"]

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"
RAW = "פרגולה"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def docs_url():
    handler = functools.partial(_Quiet, directory=str(DOCS))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.mark.parametrize("lang", ["fr", "ar", "am"])
def test_type_select_shows_translation_keeps_raw_value(browser, docs_url, lang):
    pg = browser.new_page()
    try:
        pg.goto(f"{docs_url}/{lang}/permits.html", wait_until="load")
        pg.wait_for_function("document.querySelectorAll('#pfsug option').length > 5")
        want = i18n.t(lang, i18n.PERMIT_SUG_KEYS[RAW])
        opts = pg.eval_on_selector_all(
            "#pfsug option", "o=>o.map(x=>[x.value,x.textContent])"
        )
        assert [RAW, want] in [list(o) for o in opts]
        pg.select_option("#pfsug", RAW)
        assert pg.locator("#pfsug").input_value() == RAW
        pg.check("#pfclosed")
        pg.wait_for_timeout(800)
        cells = pg.eval_on_selector_all(
            "#permits-table tbody tr:not(.filtered-out)",
            "r=>r.map(x=>[x.getAttribute('data-sug'),x.children[3].textContent])",
        )
        assert cells, "no rows after filtering by the raw type value"
        assert {tuple(c) for c in cells} == {(RAW, want)}
    finally:
        pg.close()
