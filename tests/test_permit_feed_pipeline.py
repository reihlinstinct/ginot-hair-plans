"""Offline permit pipeline tests split by responsibility.

No network and no VPN: the municipality call and the mirror fetch are
replaced with small synthetic responses shaped like the real ones (field
names taken from the parsing code). The point is the logic around them:
parsing, merging, resume/carry-over, stop-on-challenge, privacy stripping.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
VPN = ROOT / "scripts" / "vpn"
sys.path.insert(0, str(VPN))
sys.path.insert(0, str(ROOT / "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


feed = load("permit_feed", VPN / "permit_feed.py")
enrich = load("permit_enrich_mod", VPN / "permit_enrich.py")
mirror = load("mirror_ingest_mod", ROOT / "scripts" / "mirror_ingest.py")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(feed.time, "sleep", lambda *_: None)
    monkeypatch.setattr(enrich.time, "sleep", lambda *_: None)
    monkeypatch.setattr(mirror.time, "sleep", lambda *_: None)


# Section: Feed parsing and checkpoint behavior


def test_ddmmyyyy_parses_and_rejects():
    assert feed.ddmmyyyy("04/10/2026") == "2026-10-04"
    assert feed.ddmmyyyy(" 4/1/2026 ") == "2026-01-04"
    for bad in ("", None, "2026-10-04", "31/13", "a/b/c"):
        assert feed.ddmmyyyy(bad) == ""


def steps(*rows):
    return [{"stepCodeText": s, "execDateStr": e, "planDateStr": p} for s, e, p in rows]


def test_publication_dates_prefers_exec_over_plan(monkeypatch):
    rows = steps(
        (feed.PUB_START_STEP, "01/02/2026", "05/02/2026"),
        (feed.PUB_END_STEP, "", "20/02/2026"),
        ("other step", "01/01/2026", ""),
    )
    monkeypatch.setattr(feed, "call", lambda *a: rows)
    assert feed.publication_dates("1/1") == ("2026-02-01", "2026-02-20")


@pytest.mark.parametrize("payload", [None, {}, "x", []])
def test_publication_dates_tolerates_odd_payloads(monkeypatch, payload):
    monkeypatch.setattr(feed, "call", lambda *a: payload)
    assert feed.publication_dates("1/1") == ("", "")


def test_address_of_preserves_raw_fields(monkeypatch):
    # #408: provenance is preserved; joining/display is the renderer's call
    monkeypatch.setattr(
        feed,
        "call",
        lambda *a: [{"rehovName": "אלפסי", "mispBait": 9, "schunaName": "גינות העיר"}],
    )
    assert feed.address_of("1/1") == {
        "rehovName": "אלפסי",
        "mispBait": "9",
        "schunaName": "גינות העיר",
    }
    monkeypatch.setattr(feed, "call", lambda *a: None)
    assert feed.address_of("1/1") == {"rehovName": "", "mispBait": "", "schunaName": ""}


def test_street_address_only_when_street_exists():
    # a neighborhood name is not an address (#408)
    assert feed.street_address({"rehovName": "אלפסי", "mispBait": "9"}) == "אלפסי 9"
    assert feed.street_address({"rehovName": "אלפסי"}) == "אלפסי"
    assert feed.street_address({"rehovName": "", "schunaName": "גינות העיר"}) == ""
    assert feed.street_address({"rehovName": "", "mispBait": "9"}) == ""


def fake_curl(body):
    def run(cmd, **kw):
        pathlib.Path("/tmp/permit_feed_body").write_bytes(body)
        return subprocess.CompletedProcess(cmd, 0, "200", "")

    return run


def test_call_returns_json(monkeypatch):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(b'[{"a": 1}]'))
    assert feed.call(1, {}) == [{"a": 1}]


def test_call_garbage_body_is_none(monkeypatch):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(b"<html>nope</html>"))
    assert feed.call(1, {}) is None


@pytest.mark.parametrize(
    "marker", [b"<script src=incapsula>", b"Please solve the reCAPTCHA", b"px-captcha"]
)
def test_call_stops_on_challenge(monkeypatch, marker):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(marker))
    with pytest.raises(RuntimeError):
        feed.call(1, {})


def test_call_access_denied(monkeypatch):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(b"Access Denied"))
    with pytest.raises(PermissionError):
        feed.call(1, {})


def parcels_file(tmp_path, pairs):
    gj = {
        "features": [{"properties": {"gush": g, "helka": h}} for g, h in pairs]
        + [{"properties": {"gush": None, "helka": 3}}]
    }
    p = tmp_path / "parcels.geojson"
    p.write_text(json.dumps(gj))
    return p


def search_row(tik, status="הוכנה טיוטת היתר בניה"):
    return {
        "tik_num": tik,
        "mahut_bakasha": " בקשה ",
        "teurSugbakasha": "היתר",
        "teurStatus": status,
        "taarih_status": "02/03/2026",
    }


def run_feed(monkeypatch, tmp_path, argv, call_fn):
    monkeypatch.setattr(feed, "call", call_fn)
    monkeypatch.setattr(sys, "argv", ["permit_feed.py"] + argv)
    return feed.main()


def test_feed_main_scans_merges_and_carries_over(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1), (100, 2)])
    out = tmp_path / "out.json"
    out.write_text(json.dumps({"requests": [{"tik_num": "OLD/1", "status": "old"}]}))

    def call(proc, params):
        if proc == 242700437:
            return [search_row(f"T/{params['helka']}")]
        if proc == 242700451:
            return steps((feed.PUB_START_STEP, "01/02/2026", ""))
        return [{"rehovName": "רחוב", "mispBait": 1}]

    rc = run_feed(
        monkeypatch,
        tmp_path,
        ["--parcels", str(parcels), "--out", str(out), "--limit", "2"],
        call,
    )
    assert rc == 0
    data = json.loads(out.read_text())
    tiks = [r["tik_num"] for r in data["requests"]]
    assert tiks == sorted(tiks) and set(tiks) == {"OLD/1", "T/1", "T/2"}
    new = next(r for r in data["requests"] if r["tik_num"] == "T/1")
    assert new["mahut"] == "בקשה" and new["status_date"] == "2026-03-02"
    assert new["publication_start"] == "2026-02-01" and new["address"] == "רחוב 1"
    assert data["batch"] == {"offset": 0, "limit": 2}


def test_feed_main_fresh_rows_win_over_previous(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"
    out.write_text(json.dumps({"requests": [{"tik_num": "T/1", "status": "stale"}]}))
    call = lambda proc, p: [search_row("T/1", "fresh")] if proc == 242700437 else []
    run_feed(
        monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call
    )
    row = json.loads(out.read_text())["requests"][0]
    assert row["status"] == "fresh"


def test_feed_main_stops_on_challenge_without_writing(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"

    def call(*a):
        raise RuntimeError("anti_bot_challenge")

    assert (
        run_feed(
            monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call
        )
        == 2
    )
    assert not out.exists()


def test_feed_main_aborts_after_repeated_failures(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, h) for h in range(1, 10)])
    out = tmp_path / "out.json"
    rc = run_feed(
        monkeypatch,
        tmp_path,
        ["--parcels", str(parcels), "--out", str(out), "--limit", "9"],
        lambda *a: None,
    )
    assert rc == 1 and not out.exists()


def test_feed_main_keeps_alfasi_parcel_in_every_batch(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1), (100, 2), (30025, 126)])
    seen = []

    def call(proc, params):
        if proc == 242700437:
            seen.append((params["gush"], params["helka"]))
        return []

    run_feed(
        monkeypatch,
        tmp_path,
        ["--parcels", str(parcels), "--out", str(tmp_path / "o.json"), "--limit", "1"],
        call,
    )
    assert (30025, 126) in seen and (100, 1) in seen


def test_feed_detail_failure_is_not_fatal(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"

    def call(proc, params):
        if proc == 242700437:
            return [search_row("T/1")]
        raise ValueError("boom")

    assert (
        run_feed(
            monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call
        )
        == 0
    )
    assert json.loads(out.read_text())["requests"][0]["tik_num"] == "T/1"


def test_checkpoint_large_payload_uses_stdin_not_argv(monkeypatch):
    payload = {"content": "x" * 300000}
    seen = {}

    def run(cmd, **kwargs):
        seen.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, '{"commit": {"sha": "ok"}}', "")

    monkeypatch.setattr(feed.subprocess, "run", run)
    assert feed.gh_api("PUT", "/repos/test/test/contents/data.json", "test", payload)[
        "commit"
    ]
    assert "@-" in seen["cmd"]
    assert max(map(len, seen["cmd"])) < 1000
    assert json.loads(seen["kwargs"]["input"]) == payload


@pytest.mark.parametrize(
    "age,status,complete,reuse",
    [
        ("today", "fresh", True, True),
        ("2000-01-01", "fresh", True, False),
        ("today", "old", True, False),
        ("today", "fresh", False, False),
        (None, "fresh", True, False),
    ],
)
def test_feed_reuses_only_complete_same_day_unchanged_details(
    monkeypatch, tmp_path, age, status, complete, reuse
):
    # Pin the feed's operative date: the module stamps in Asia/Jerusalem
    # (issue #331), so a naive date.today() races the runner's UTC date.
    fixed_today = feed.datetime.date(2026, 3, 9)
    monkeypatch.setattr(feed, "_today", lambda: fixed_today)
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"
    prior = {
        "tik_num": "T/1",
        "mahut": "בקשה",
        "sugbakasha": "היתר",
        "status": status,
        "status_date": "2026-03-02",
        "publication_start": "2026-02-01",
        "publication_end_planned": "",
        "address": "cached",
    }
    if age:
        prior["details_checked_on"] = fixed_today.isoformat() if age == "today" else age
    if not complete:
        del prior["address"]
    out.write_text(json.dumps({"requests": [prior]}))
    seen = []

    def call(proc, params):
        seen.append(proc)
        return [search_row("T/1", "fresh")] if proc == 242700437 else []

    assert (
        run_feed(
            monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call
        )
        == 0
    )
    assert (242700451 not in seen) == reuse
    row = json.loads(out.read_text())["requests"][0]
    assert row["details_checked_on"] == fixed_today.isoformat()
    assert row["address"] == ("cached" if reuse else "")


def test_inverted_publication_dates_counted():
    # #463: source anomaly rows (planned end before publication start) are
    # preserved as-is but counted for the run summary.
    rows = [
        {"publication_start": "2026-11-24", "publication_end_planned": "2026-10-18"},
        {"publication_start": "2026-10-18", "publication_end_planned": "2026-11-24"},
        {"publication_start": "", "publication_end_planned": "2026-11-24"},
        {"publication_start": "18.10.2026", "publication_end_planned": "24.11.2026"},
        {"publication_start": 20261124, "publication_end_planned": 20261018},
        {"publication_start": "2026-02-31", "publication_end_planned": "2026-02-30"},
        {"publication_start": ["2026-11-24"], "publication_end_planned": None},
    ]
    assert feed.count_inverted_publication_dates(rows) == 1
