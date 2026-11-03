"""Parity guard for the triplicated TERMINAL_STATUSES constant (#807).

mirror_ingest.py, scripts/vpn/permit_enrich.py and scripts/vpn/recheck_select.py
each keep their own copy (the VPN modules must stay import-free of one
another). They must never drift: the queue writer and the enrichment consumer
disagreeing on what is terminal reopens the class of loss #799 fixed.

src/ginot/page.py keeps a separate display-side set. Its current difference
from the ingest set is exactly {"נדחתה"}: rejected requests stay visible as
active on the site while the enrichment queue prunes them. Pin the difference
so a silent change in either direction fails here; if the site set is meant
to match, update both and remove the difference pin.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    path = ROOT / rel
    # permit_enrich imports its sibling permit_feed; make it resolvable.
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(path.parent))


def test_script_copies_are_identical():
    ingest = _load("mirror_ingest", "scripts/mirror_ingest.py")
    enrich = _load("permit_enrich", "scripts/vpn/permit_enrich.py")
    recheck = _load("recheck_select", "scripts/vpn/recheck_select.py")
    assert ingest.TERMINAL_STATUSES == enrich.TERMINAL_STATUSES
    assert enrich.TERMINAL_STATUSES == recheck.TERMINAL_STATUSES


def test_page_display_set_difference_is_pinned():
    ingest = _load("mirror_ingest", "scripts/mirror_ingest.py")
    from ginot.page import _PERMIT_TERMINAL_STATUSES

    assert set(_PERMIT_TERMINAL_STATUSES) <= ingest.TERMINAL_STATUSES
    assert ingest.TERMINAL_STATUSES - set(_PERMIT_TERMINAL_STATUSES) == {"נדחתה"}
