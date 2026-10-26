"""Unit tests for the Rishui149 active-publications fetch (issue #519).

No network: parsing, normalization, new-publication detection, tracked-area
filtering and the stop-on-challenge contract are tested on fixtures.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "rishui_publish_u", ROOT / "scripts/vpn/rishui_publish.py"
)
rishui_publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rishui_publish)

RAW_ROW = {
    "myIndex": 16530017,
    "tik_num": "2026/0439.00",
    "description": None,
    "schn": "קטמון הישנה",
    "teur_makom": None,
    "rehov": "הפלמח",
    "misp_bait": "41",
    "ED700": "2026-09-24T00:00:00",
    "ED800": "2026-10-18T00:00:00",
    "PD900": "2026-11-13T00:00:00",
    "connectedRecID": None,
    "DocId": None,
}


def test_parse_rows_normalizes_fields():
    rows = rishui_publish.parse_rows(json.dumps([RAW_ROW]))
    assert rows == [
        {
            "myIndex": 16530017,
            "tik_num": "2026/0439.00",
            "street": "הפלמח",
            "house_number": "41",
            "neighborhood": "קטמון הישנה",
            "place_description": None,
            "publication_date": "2026-10-18",
            "objection_deadline": "2026-11-13",
            "ed700": "2026-09-24",
            "connected_rec_id": None,
            "doc_id": None,
        }
    ]


def test_parse_rows_handles_missing_dates():
    item = dict(RAW_ROW, PD900=None, ED700=None)
    rows = rishui_publish.parse_rows(json.dumps([item]))
    assert rows[0]["objection_deadline"] is None
    assert rows[0]["ed700"] is None


def test_parse_rows_rejects_non_list():
    with pytest.raises(ValueError):
        rishui_publish.parse_rows('{"rows": []}')


def test_parse_rows_rejects_bad_row_shape():
    with pytest.raises(ValueError):
        rishui_publish.parse_rows('[{"tik_num": "2026/0439.00"}]')


def test_detect_new_by_myindex():
    old = [{"myIndex": 1}, {"myIndex": 2}]
    new = [{"myIndex": 2}, {"myIndex": 3}]
    assert rishui_publish.detect_new(old, new) == [{"myIndex": 3}]


def test_filter_tracked_keeps_council_neighborhoods():
    rows = [
        {"neighborhood": "קטמון הישנה"},
        {"neighborhood": "רחביה"},
        {"neighborhood": "רמות"},
        {"neighborhood": None},
    ]
    kept = rishui_publish.filter_tracked(rows)
    assert [r["neighborhood"] for r in kept] == ["קטמון הישנה", "רחביה"]


def test_challenge_on_status():
    assert rishui_publish.is_challenge(403, "")
    assert rishui_publish.is_challenge(429, "")
    assert rishui_publish.is_challenge(503, "")
    assert not rishui_publish.is_challenge(200, "[]")


def test_challenge_on_body_markers():
    assert rishui_publish.is_challenge(200, "<title>Access Denied</title>")
    assert rishui_publish.is_challenge(200, "akamai bot manager")
    assert not rishui_publish.is_challenge(200, json.dumps([RAW_ROW], ensure_ascii=False))


def test_summarize_lists_tracked_with_deadline():
    rows = rishui_publish.parse_rows(json.dumps([RAW_ROW]))
    text = rishui_publish.summarize(rows)
    assert "active publications: 1" in text
    assert "2026/0439.00" in text
    assert "deadline 2026-11-13" in text


def test_probe_workflow_keeps_stop_on_challenge_contract():
    """The probe must run through the tunnel, make the single fetch, upload the
    artifact, and always tear the tunnel down (issue #519)."""
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/rishui-publish-probe.yml"
    ).read_text()
    assert "workflow_dispatch" in workflow
    assert "scripts/vpn/l2tp.py up" in workflow
    assert "scripts/vpn/rishui_publish.py fetch --out publish-api.json" in workflow
    assert "if: always()" in workflow
    assert "scripts/vpn/l2tp.py down" in workflow
