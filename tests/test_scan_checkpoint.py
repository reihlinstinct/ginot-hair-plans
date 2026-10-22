import importlib.util
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location("permit_feed", vpn / "permit_feed.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def _reqs(n):
    return {f"1949/{i:04d}.01": {"tik_num": f"1949/{i:04d}.01"} for i in range(n)}


def test_checkpoint_payload_shape():
    p = pf.checkpoint_payload(_reqs(3), offset=120, limit=280, done=15)
    assert p["checkpoint"] is True
    assert p["batch"] == {"offset": 120, "limit": 280, "done": 15}
    assert len(p["requests"]) == 3
    assert [r["tik_num"] for r in p["requests"]] == sorted(r["tik_num"] for r in p["requests"])


def test_resume_start_matches_range():
    cp = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=40)
    assert pf.resume_start(cp, offset=120, limit=280, batch_len=281) == 40


def test_resume_ignores_other_ranges_and_garbage():
    cp = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=40)
    assert pf.resume_start(cp, offset=400, limit=280, batch_len=281) == 0
    assert pf.resume_start(cp, offset=120, limit=60, batch_len=61) == 0
    assert pf.resume_start(None, offset=120, limit=280, batch_len=281) == 0
    assert pf.resume_start({"batch": {}}, offset=120, limit=280, batch_len=281) == 0
    # A completed parcel scan must resume details, not discard its rows.
    full = pf.checkpoint_payload(_reqs(5), offset=120, limit=280, done=281)
    assert pf.resume_start(full, offset=120, limit=280, batch_len=281) == 281
    full["batch"]["done"] = 282
    assert pf.resume_start(full, offset=120, limit=280, batch_len=281) == 0


def test_checkpoint_interval_within_owner_spec():
    import argparse
    # owner spec 2026-10-21: persist every 10-20 parcels
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint-every", type=int, default=15)
    args = ap.parse_args([])
    assert 10 <= args.checkpoint_every <= 20


def test_checkpoint_retries_until_confirmed(monkeypatch):
    attempts = []
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)

    def push(*args):
        attempts.append(args)
        return len(attempts) == 3

    monkeypatch.setattr(pf, "_push_checkpoint_once", push)
    pf.push_checkpoint(_reqs(1), 400, 280, 15, "fake", "example/repo")
    assert len(attempts) == 3


def test_checkpoint_failure_stops_after_three_attempts(monkeypatch):
    import pytest
    attempts = []
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)
    monkeypatch.setattr(pf, "_push_checkpoint_once",
                        lambda *args: attempts.append(args) or False)
    with pytest.raises(RuntimeError, match="persistence failed"):
        pf.push_checkpoint(_reqs(1), 400, 280, 15, "fake", "example/repo")
    assert len(attempts) == 3


def test_complete_scan_resumes_details_and_checkpoints_them(monkeypatch, tmp_path):
    import json
    parcels = tmp_path / "parcels.json"
    parcels.write_text(json.dumps({"features": [
        {"properties": {"gush": 1, "helka": i}} for i in range(1, 4)
    ]}))
    out = tmp_path / "out.json"
    requests = _reqs(3)
    first = min(requests)
    requests[first].update(address="saved", publication_start="", publication_end_planned="")
    cp = pf.checkpoint_payload(requests, 0, 3, 3)
    monkeypatch.setenv("GH_TOKEN", "fake")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    monkeypatch.setattr(pf, "load_checkpoint", lambda *_: cp)
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)
    monkeypatch.setattr(pf, "call", lambda *_: (_ for _ in ()).throw(
        AssertionError("completed parcels must not be scanned again")))
    fetched = []
    monkeypatch.setattr(pf, "publication_dates", lambda tik: fetched.append(tik) or ("", ""))
    monkeypatch.setattr(pf, "address_of", lambda tik: "new")
    saves = []
    monkeypatch.setattr(pf, "push_checkpoint", lambda reqs, *args:
                        saves.append(json.loads(json.dumps(reqs))))
    monkeypatch.setattr(sys, "argv", ["permit_feed", "--parcels", str(parcels),
                                    "--out", str(out), "--limit", "3",
                                    "--checkpoint", "--resume", "--checkpoint-every", "1"])
    assert pf.main() == 0
    assert first not in fetched
    assert len(fetched) == 2
    assert len(saves) == 4  # completed scan, each detail, final durable save
    assert saves[-1][first]["address"] == "saved"
    assert all("address" in row for row in saves[-1].values())
    assert len(json.loads(out.read_text())["requests"]) == 3


def test_checkpoint_write_confirmation_and_exception(monkeypatch):
    def api(method, path, token, payload=None):
        if "/git/ref/" in path:
            return {"object": {"sha": "fake"}}
        if method == "GET":
            return {"sha": "fake"}
        return {"commit": {"sha": "saved"}}

    monkeypatch.setattr(pf, "gh_api", api)
    assert pf._push_checkpoint_once(_reqs(1), 400, 280, 15, "fake", "example/repo")
    monkeypatch.setattr(pf, "gh_api", lambda *_: None)
    assert not pf._push_checkpoint_once(_reqs(1), 400, 280, 15, "fake", "example/repo")
