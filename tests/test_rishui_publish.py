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


def test_resolve_in_polygon_requires_neighborhood_and_parcel():
    rows = [
        {"tik_num": "a", "neighborhood": "קטמון הישנה"},
        {"tik_num": "b", "neighborhood": "גוננים"},  # in polygon but out of the 7
        {"tik_num": "c", "neighborhood": "רחביה"},  # parcel outside polygon
        {"tik_num": "d", "neighborhood": None},  # unknown tik -> unresolved
    ]
    tik_parcels = {"a": (1, 1), "b": (1, 2), "c": (9, 9)}
    parcel_keys = {(1, 1), (1, 2)}
    rishui_publish.resolve_in_polygon(rows, tik_parcels, parcel_keys)
    assert [r["in_polygon"] for r in rows] == [True, False, False, None]


def test_scope_schn_is_the_seven_council_neighborhoods():
    assert "גבעת מרדכי" not in rishui_publish.SCOPE_SCHN
    assert "ימין משה" not in rishui_publish.SCOPE_SCHN
    assert "גוננים" not in rishui_publish.SCOPE_SCHN
    for name in ("קטמון הישנה", "רחביה", "מושבה גרמנית", "המושבה היוונית",
                 "קריית שמואל", "טלביה", "נוה שאנן/ניות"):
        assert name in rishui_publish.SCOPE_SCHN


def test_challenge_on_status():
    assert rishui_publish.is_challenge(403, "")
    assert rishui_publish.is_challenge(429, "")
    assert rishui_publish.is_challenge(503, "")
    assert not rishui_publish.is_challenge(200, "[]")


def test_challenge_on_body_markers():
    assert rishui_publish.is_challenge(200, "<title>Access Denied</title>")
    assert rishui_publish.is_challenge(200, "akamai bot manager")
    assert not rishui_publish.is_challenge(200, json.dumps([RAW_ROW], ensure_ascii=False))


def test_summarize_lists_in_polygon_with_deadline():
    rows = rishui_publish.parse_rows(json.dumps([RAW_ROW]))
    rows[0]["in_polygon"] = True
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


def test_parse_rows_rejects_null_or_container_keys():
    """myIndex is the dedup key and tik_num the permit join key: null or
    container values must be rejected, not silently deduped/printed."""
    for bad in (None, [], {}, True, ""):
        row = dict(RAW_ROW, myIndex=bad)
        with pytest.raises(ValueError):
            rishui_publish.parse_rows(json.dumps([row]))
    for bad in (None, 123, [], ""):
        row = dict(RAW_ROW, tik_num=bad)
        with pytest.raises(ValueError):
            rishui_publish.parse_rows(json.dumps([row]))
    # int and str myIndex are both fine (the live API returns ints)
    assert len(rishui_publish.parse_rows(json.dumps([RAW_ROW]))) == 1
    assert len(rishui_publish.parse_rows(json.dumps([dict(RAW_ROW, myIndex="x1")]))) == 1


def test_fetch_hard_stops_on_redirect():
    """Single-GET contract: a redirect must not be followed (CodeRabbit #528)."""
    import urllib.error

    class _Resp:
        status = 200
        def read(self):
            return b"[]"
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    calls = []

    def fake_open(req, timeout=40):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 302, "Found", {"Location": "https://evil/"}, None)

    rishui_publish._OPENER.open = fake_open
    try:
        with pytest.raises(rishui_publish.ChallengeError):
            rishui_publish.fetch_publish("https://example/x")
    finally:
        pass
    assert calls == ["https://example/x"]  # exactly one attempt, no follow


def test_main_returns_2_on_challenge(tmp_path, capsys):
    """Stop-on-challenge contract at the CLI boundary: exit 2, no output file."""
    def boom(*a, **k):
        raise rishui_publish.ChallengeError("HTTP 503")

    orig = rishui_publish.fetch_publish
    rishui_publish.fetch_publish = boom
    try:
        rc = rishui_publish.main(["fetch", "--out", str(tmp_path / "o.json")])
    finally:
        rishui_publish.fetch_publish = orig
    assert rc == 2
    assert not (tmp_path / "o.json").exists()
    assert "CHALLENGE" in capsys.readouterr().err
