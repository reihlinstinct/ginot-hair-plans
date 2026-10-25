"""Audit ingest validation tests (issue #439): callback must match immutable source."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "audit_ingest", ROOT / "scripts/audit/ingest.py"
)
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)

FEED = json.dumps({"batch": {"offset": 100, "limit": 50}, "requests": []}).encode()
DIGEST = hashlib.sha256(FEED).hexdigest()
SHA = "a" * 40


def report(**over):
    base = {
        "schema_version": 1,
        "source_run": "40147963746",
        "auditor_run": "40147963747",
        "source_commit": SHA,
        "source_digest": DIGEST,
        "total_unique_parcels": 200,
        "published_cursor": 150,
        "remaining": 50,
    }
    base.update(over)
    return base


def test_validate_happy_path_canonical_output():
    out = ai.validate(report(), FEED, FEED)
    assert out["cursor_percent"] == 75.0
    assert out["published_cursor"] == 150 and out["remaining"] == 50
    # canonical warning always present; callback strings never rendered
    assert "not proof" in out["warning"]


def test_validate_cursor_capped_at_total():
    feed = json.dumps({"batch": {"offset": 190, "limit": 50}, "requests": []}).encode()
    digest = hashlib.sha256(feed).hexdigest()
    r = report(source_digest=digest, published_cursor=200, remaining=0)
    out = ai.validate(r, feed, feed)
    assert out["published_cursor"] == 200


@pytest.mark.parametrize(
    "mut,msg",
    [
        ({"schema_version": 2}, "schema"),
        ({"source_run": "abc"}, "run identifier"),
        ({"auditor_run": ""}, "run identifier"),
        ({"source_commit": "xyz"}, "commit"),
        ({"source_digest": "0" * 64}, "digest mismatch"),
        ({"total_unique_parcels": 0}, "total"),
        ({"total_unique_parcels": "200"}, "total"),
        ({"published_cursor": 149}, "Cursor arithmetic"),
        ({"remaining": 51}, "Cursor arithmetic"),
    ],
)
def test_validate_rejects_bad_reports(mut, msg):
    with pytest.raises(ValueError, match=msg):
        ai.validate(report(**mut), FEED, FEED)


def test_validate_rejects_stale_current():
    other = json.dumps({"batch": {"offset": 0, "limit": 50}, "requests": []}).encode()
    with pytest.raises(ValueError, match="Stale audit"):
        ai.validate(report(), FEED, other)


def test_main_end_to_end_with_mocked_git(tmp_path, monkeypatch):
    """main(): git-show mocked, parcel total cross-checked, both outputs written."""
    geojson = json.dumps({
        "features": [
            {"properties": {"gush": 1, "helka": 1}},
            {"properties": {"gush": 2, "helka": 2}},
        ]
    }).encode()
    feed = json.dumps({"batch": {"offset": 1, "limit": 1}, "requests": []}).encode()
    digest = hashlib.sha256(feed).hexdigest()

    class _R:
        def __init__(self, out):
            self.stdout = out

    def fake_run(cmd, **kw):
        target = cmd[-1]
        if "permit_requests.json" in target:
            return _R(feed)
        return _R(geojson)

    monkeypatch.setattr(ai.subprocess, "run", fake_run)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/permit_requests.json").write_bytes(feed)
    (tmp_path / "docs").mkdir()
    rep = tmp_path / "report.json"
    rep.write_text(json.dumps(report(
        source_digest=digest, total_unique_parcels=2,
        published_cursor=2, remaining=0,
    )))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["ingest.py", "--report", str(rep)])
    ai.main()
    written = json.loads((tmp_path / "data/parcel_audit.json").read_text())
    assert written["total_unique_parcels"] == 2
    assert (tmp_path / "docs/parcel-audit.json").exists()


def test_main_rejects_oversized_and_mismatched_total(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    big = tmp_path / "big.json"
    big.write_text(" " * 6001)
    monkeypatch.setattr("sys.argv", ["ingest.py", "--report", str(big)])
    with pytest.raises(ValueError, match="Oversized"):
        ai.main()

    geojson = json.dumps({"features": [{"properties": {"gush": 1, "helka": 1}}]}).encode()

    class _R:
        def __init__(self, out):
            self.stdout = out

    monkeypatch.setattr(
        ai.subprocess,
        "run",
        lambda cmd, **kw: _R(geojson if "geojson" in cmd[-1] else FEED),
    )
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps(report(total_unique_parcels=999)))
    monkeypatch.setattr("sys.argv", ["ingest.py", "--report", str(rep)])
    with pytest.raises(ValueError, match="Parcel total mismatch"):
        ai.main()
