"""Every generated page fetches permit-ids.json from the right place (#1175).

page.py ships one JS block for all languages and rewrites its fetch() paths
per language page with str.replace. A replace that silently stops matching
would leave a language page requesting a file that does not exist, and the
page would then fall back to the full-table download this guard exists to
avoid. permit-ids.json lives at docs/ root, so the root page uses a bare path
and each language page ('en', 'ar', ...) goes up one level.
"""

import pathlib
import re

DOCS = pathlib.Path(__file__).parent.parent / "docs"
PAGES = sorted(DOCS.glob("index.html")) + sorted(DOCS.glob("*/index.html"))
LANG_PAGES = [p for p in PAGES if p.parent != DOCS]


def _permit_ids_fetches(page):
    return re.findall(r"fetch\('([^']*permit-ids\.json)'\)", page.read_text("utf-8"))


def test_pages_are_found():
    assert (DOCS / "index.html") in PAGES
    assert len(LANG_PAGES) >= 4


def test_root_page_fetches_permit_ids_without_prefix():
    assert _permit_ids_fetches(DOCS / "index.html") == ["permit-ids.json"]


def test_language_pages_fetch_permit_ids_from_the_docs_root():
    for page in LANG_PAGES:
        assert _permit_ids_fetches(page) == ["../permit-ids.json"], page


def test_every_referenced_permit_ids_path_exists():
    assert (DOCS / "permit-ids.json").is_file()
    for page in PAGES:
        for ref in _permit_ids_fetches(page):
            assert (page.parent / ref).resolve() == (DOCS / "permit-ids.json").resolve()
