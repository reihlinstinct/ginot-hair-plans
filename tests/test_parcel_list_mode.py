"""Tiered re-check B (issue #344): permit_feed --parcel-list. No network."""
import importlib.util
import json
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location("permit_feed_pl", vpn / "permit_feed.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def _setup(tmp_path, monkeypatch, with_prior_address=True):
    parcels = tmp_path / "parcels.geojson"
    parcels.write_text(json.dumps({"features": [
        {"properties": {"gush": 1, "helka": 1}}, {"properties": {"gush": 2, "helka": 2}}]}))
    plist = tmp_path / "list.json"
    plist.write_text(json.dumps([[2, 2], [9, 9], [2, 2]]))  # unknown parcel and duplicate
    out = tmp_path / "feed.json"
    prior = {"tik_num": "T1", "status": "old", "gush": 2, "helka": 2}
    if with_prior_address:
        prior["address"] = "Cached St 1"
    out.write_text(json.dumps({"batch": {"offset": 680, "limit": 280}, "requests": [prior]}))
    scanned = []
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)
    monkeypatch.setattr(pf, "call", lambda proc, params: scanned.append((params["gush"], params["helka"]))
                        or [{"tik_num": "T1", "teurStatus": "new", "taarih_status": "01/01/2026"}])
    monkeypatch.setattr(pf, "publication_dates", lambda tik: ("2026-10-01", "2026-12-01"))
    addr = []
    monkeypatch.setattr(pf, "address_of", lambda tik: addr.append(tik) or "Fetched St 2")
    monkeypatch.setenv("GH_TOKEN", "fake")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    monkeypatch.setattr(pf, "load_checkpoint", lambda *_: (_ for _ in ()).throw(
        AssertionError("list mode must not read the scan checkpoint")))
    monkeypatch.setattr(pf, "push_checkpoint", lambda *a: (_ for _ in ()).throw(
        AssertionError("list mode must not write the scan checkpoint")))
    monkeypatch.setattr(sys, "argv", ["permit_feed", "--parcels", str(parcels), "--out", str(out),
                                    "--parcel-list", str(plist), "--checkpoint", "--resume"])
    return out, scanned, addr


def test_parcel_list_scans_only_listed_known_parcels(tmp_path, monkeypatch):
    _out, scanned, _ = _setup(tmp_path, monkeypatch)
    assert pf.main() == 0
    assert scanned == [(2, 2)]


def test_parcel_list_keeps_backfill_cursor_untouched(tmp_path, monkeypatch):
    """Regression: a re-check must not move the offset backfill cursor."""
    out, _, _ = _setup(tmp_path, monkeypatch)
    assert pf.main() == 0
    assert json.loads(out.read_text())["batch"] == {"offset": 680, "limit": 280}


def test_parcel_list_reuses_cached_address_and_refreshes_status(tmp_path, monkeypatch):
    out, _, addr = _setup(tmp_path, monkeypatch)
    assert pf.main() == 0
    row = json.loads(out.read_text())["requests"][0]
    assert addr == [] and row["address"] == "Cached St 1"
    assert row["status"] == "new" and row["publication_start"] == "2026-10-01"


def test_parcel_list_fetches_address_when_not_cached(tmp_path, monkeypatch):
    _out, _, addr = _setup(tmp_path, monkeypatch, with_prior_address=False)
    assert pf.main() == 0
    assert addr == ["T1"]
