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
    row = dict(rows[0])
    diagnostics = row.pop("diagnostics")
    assert row == {
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
    assert diagnostics["fields"]["PD900"] == {
        "present": True,
        "null": False,
        "type": "str",
        "date_like": True,
    }
    assert diagnostics["raw"]["PD900"] == RAW_ROW["PD900"]


def _diag(item):
    return rishui_publish.parse_rows(json.dumps([item]))[0]["diagnostics"]


def test_diagnostics_distinguish_missing_null_and_value():
    missing = _diag({k: v for k, v in RAW_ROW.items() if k != "PD900"})
    assert missing["fields"]["PD900"] == {
        "present": False,
        "null": False,
        "type": "missing",
    }
    assert missing["raw"]["PD900"] is None

    null_row = _diag(dict(RAW_ROW, PD900=None))
    assert null_row["fields"]["PD900"]["present"] is True
    assert null_row["fields"]["PD900"]["null"] is True

    valued = _diag(RAW_ROW)
    assert valued["fields"]["PD900"]["present"] is True
    assert valued["fields"]["PD900"]["null"] is False
    assert valued["raw"]["PD900"] == RAW_ROW["PD900"]


def test_diagnostics_flag_renamed_key():
    # PD900 renamed upstream to PD901: expected key missing AND the new key
    # name surfaces in unexpected_keys, so the rename is detectable instead of
    # looking like a run of null deadlines.
    item = {k: v for k, v in RAW_ROW.items() if k != "PD900"}
    item["PD901"] = "2026-11-13"
    diag = _diag(item)
    assert diag["fields"]["PD900"]["present"] is False
    assert "PD901" in diag["unexpected_keys"]


def test_diagnostics_flag_invalid_date_format():
    diag = _diag(dict(RAW_ROW, PD900="13/11/2026"))
    assert diag["fields"]["PD900"]["date_like"] is False
    assert diag["raw"]["PD900"] == {"omitted": "str"}
    typed = _diag(dict(RAW_ROW, DocId={"id": 5}))
    assert typed["fields"]["DocId"]["type"] == "dict"
    assert typed["raw"]["DocId"] == {"omitted": "dict"}


def test_diagnostics_raw_copy_is_bounded():
    # Containers and oversized values in tracked fields are never copied raw:
    # the drift stays visible via fields[] without storing unreviewed payloads.
    diag = _diag(
        dict(
            RAW_ROW,
            PD900=["2026-11-13"],
            DocId="x" * 500,
            ED800={"d": 1},
            ED700="2026-09-24T10:11:12" + "e" * 100,
        )
    )
    assert diag["raw"]["PD900"] == {"omitted": "list"}
    assert diag["raw"]["DocId"] == {"omitted": "str"}
    assert diag["raw"]["ED800"] == {"omitted": "dict"}
    assert diag["raw"]["ED700"] == "2026-09-24T10:11:12" + "e" * 13
    assert len(diag["raw"]["ED700"]) == 32


def test_diagnostics_unexpected_keys_capped_and_counted():
    item = dict(RAW_ROW)
    for i in range(30):
        item[f"extra_{i:02d}"] = i
    item["k" * 100] = 1
    diag = _diag(item)
    expected_total = len([k for k in item if k not in rishui_publish.KNOWN_KEYS])
    assert diag["unexpected_keys_total"] == expected_total == 32
    assert len(diag["unexpected_keys"]) == 20
    assert all(len(k) <= 64 for k in diag["unexpected_keys"])


def test_parse_rows_handles_missing_dates():
    item = dict(RAW_ROW, PD900=None, ED700=None)
    rows = rishui_publish.parse_rows(json.dumps([item]))
    assert rows[0]["objection_deadline"] is None
    assert rows[0]["ed700"] is None


def test_parse_rows_rejects_non_list():
    with pytest.raises(TypeError):
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
    for name in (
        "קטמון הישנה",
        "רחביה",
        "מושבה גרמנית",
        "המושבה היוונית",
        "קריית שמואל",
        "טלביה",
        "נוה שאנן/ניות",
    ):
        assert name in rishui_publish.SCOPE_SCHN


def test_challenge_on_status():
    assert rishui_publish.is_challenge(403, "")
    assert rishui_publish.is_challenge(429, "")
    assert rishui_publish.is_challenge(503, "")
    assert not rishui_publish.is_challenge(200, "[]")


def test_challenge_on_body_markers():
    assert rishui_publish.is_challenge(200, "<title>Access Denied</title>")
    assert rishui_publish.is_challenge(200, "akamai bot manager")
    assert not rishui_publish.is_challenge(
        200, json.dumps([RAW_ROW], ensure_ascii=False)
    )


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
    assert (
        len(rishui_publish.parse_rows(json.dumps([dict(RAW_ROW, myIndex="x1")]))) == 1
    )


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
        raise urllib.error.HTTPError(
            req.full_url, 302, "Found", {"Location": "https://evil/"}, None
        )

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


@pytest.mark.parametrize("kind", ["http", "transport", "timeout"])
@pytest.mark.parametrize("existing", [False, True])
def test_main_fetch_errors_fail_closed_without_retry_or_output_change(
    tmp_path,
    capsys,
    monkeypatch,
    kind,
    existing,
):
    import urllib.error

    output = tmp_path / "baseline.json"
    if existing:
        output.write_text("preserved baseline", encoding="utf-8")
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        if kind == "http":
            raise urllib.error.HTTPError(
                "https://private.invalid", 500, "secret body", {}, None
            )
        if kind == "transport":
            raise urllib.error.URLError("private network value")
        raise TimeoutError("private timeout value")

    monkeypatch.setattr(rishui_publish, "fetch_publish", fail)
    assert rishui_publish.main(["fetch", "--out", str(output)]) == 1
    assert calls == [1]
    assert (
        output.read_text(encoding="utf-8") == "preserved baseline"
        if existing
        else not output.exists()
    )
    diagnostic = capsys.readouterr().err
    assert "FETCH_FAILED:" in diagnostic and "no retry" in diagnostic
    assert "private" not in diagnostic and "secret body" not in diagnostic
    assert "500" in diagnostic if kind == "http" else "transport" in diagnostic


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_hard_stop_status_does_not_read_error_body(
    status, tmp_path, capsys, monkeypatch
):
    import urllib.error

    class Unreadable:
        def read(self, *args):
            pytest.fail("known hard-stop status must not read body")

        def close(self):
            pass

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid", status, "private", {}, Unreadable()
        )

    monkeypatch.setattr(rishui_publish._OPENER, "open", fail)
    output = tmp_path / "baseline.json"
    output.write_text("preserved")
    assert rishui_publish.main(["fetch", "--out", str(output)]) == 2
    assert output.read_text() == "preserved"
    assert "CHALLENGE" in capsys.readouterr().err


def test_truncated_http500_has_fixed_diagnostic(tmp_path, capsys, monkeypatch):
    import http.client
    import io
    import urllib.error

    class Socket:
        def makefile(self, *args):
            return io.BytesIO(
                b"HTTP/1.1 500 PRIVATE_REASON\r\nContent-Length: 100\r\n\r\nshort"
            )

    response = http.client.HTTPResponse(Socket())
    response.begin()
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError(
            "https://example.invalid", 500, "PRIVATE_REASON", {}, response
        )

    monkeypatch.setattr(rishui_publish._OPENER, "open", fail)
    output = tmp_path / "baseline.json"
    output.write_text("preserved")
    assert rishui_publish.main(["fetch", "--out", str(output)]) == 1
    assert calls == [1]
    assert output.read_text() == "preserved"
    assert (
        capsys.readouterr().err
        == "FETCH_FAILED: malformed or incomplete HTTP response; no retry; output unchanged\n"
    )
