"""Unit coverage for scripts/vpn/mavat_check.py pure helpers."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location(
    "mavat_check", ROOT / "scripts/vpn/mavat_check.py"
)
mc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mc)


# Section: chrome-flap detection (#989)
def _prev(**kw):
    base = {
        "fingerprint": "aaaabbbbccccdddd",
        "page_chars": 5000,
        "deadline_text": "15.12.2026",
        "station_text": "הפקדה",
    }
    base.update(kw)
    return base


def _info(**kw):
    base = {
        "fingerprint": "eeeeffff00001111",
        "page_chars": 5246,  # +246: the observed chrome toggle
        "deadline_text": "15.12.2026",
        "station_text": "הפקדה",
    }
    base.update(kw)
    return base


def test_chrome_flap_exact_delta_same_fields():
    assert mc.is_chrome_flap(_prev(), _info())
    assert mc.is_chrome_flap(_prev(), _info(page_chars=5000 - 246))  # -246 too


def test_same_fingerprint_is_not_a_flap():
    assert not mc.is_chrome_flap(_prev(), _info(fingerprint="aaaabbbbccccdddd"))


def test_other_delta_sizes_still_flag():
    assert not mc.is_chrome_flap(_prev(), _info(page_chars=5247))
    assert not mc.is_chrome_flap(_prev(), _info(page_chars=5000))


def test_changed_extracted_fields_still_flag():
    assert not mc.is_chrome_flap(_prev(), _info(station_text="אישור"))
    assert not mc.is_chrome_flap(_prev(), _info(deadline_text=""))


def test_missing_page_chars_falls_back_to_flagging():
    prev = _prev()
    del prev["page_chars"]
    assert not mc.is_chrome_flap(prev, _info())
