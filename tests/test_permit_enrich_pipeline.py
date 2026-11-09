"""Offline permit pipeline tests split by responsibility.

No network and no VPN: the municipality call and the mirror fetch are
replaced with small synthetic responses shaped like the real ones (field
names taken from the parsing code). The point is the logic around them:
parsing, merging, resume/carry-over, stop-on-challenge, privacy stripping.
"""

import importlib.util
import json
import pathlib
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


def steps(*rows):
    return [{"stepCodeText": s, "execDateStr": e, "planDateStr": p} for s, e, p in rows]


# Section: Enrichment selection and failures


def mirror_file(tmp_path, rows):
    p = tmp_path / "mirror.json"
    p.write_text(json.dumps({"requests": rows}, ensure_ascii=False))
    return p


def run_enrich(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(enrich, "SPOTCHECK", str(tmp_path / "spot.json"))
    # The retry queue (issue #492) must land in tmp like the spot check:
    # a CWD-relative write would dirty the repo for the site-index test.
    monkeypatch.setattr(enrich, "PENDING", str(tmp_path / "pending.json"))
    monkeypatch.setattr(sys, "argv", ["permit_enrich.py"] + argv)
    return enrich.main()


def test_enrich_writes_dates_and_spotcheck(monkeypatch, tmp_path):
    rows = [
        {"tik_num": "1", "status": "נפתח תיק רישוי"},
        {"tik_num": "2", "status": "נפתח תיק רישוי"},
        {"tik_num": "3", "status": "הבקשה נסגרה"},
    ]
    m = mirror_file(tmp_path, rows)
    monkeypatch.setattr(
        enrich,
        "publication_dates",
        lambda t: ("2026-02-01", "2026-02-20") if t == "1" else ("", ""),
    )
    monkeypatch.setattr(enrich, "call", lambda *a: steps(("שלב", "", "01/01/2026")))
    rc = run_enrich(
        monkeypatch,
        tmp_path,
        [
            "--mirror",
            str(m),
            "--diff",
            str(tmp_path / "none.json"),
            "--include-unenriched",
        ],
    )
    assert rc == 0
    out = {r["tik_num"]: r for r in json.loads(m.read_text())["requests"]}
    assert out["1"]["publication_start"] == "2026-02-01"
    assert out["2"]["publication_start"] == ""
    assert "publication_start" not in out["3"]  # terminal status never fetched
    spot = json.loads((tmp_path / "spot.json").read_text())["samples"]
    assert [s["tik_num"] for s in spot] == ["2"]
    assert spot[0]["steps"] == [
        {"step": "שלב", "has_exec_date": False, "has_plan_date": True}
    ]


def test_enrich_stops_on_challenge_and_keeps_mirror_untouched(monkeypatch, tmp_path):
    m = mirror_file(tmp_path, [{"tik_num": "1", "status": "נפתח תיק רישוי"}])
    before = m.read_text()

    def boom(t):
        raise RuntimeError("anti_bot_challenge")

    monkeypatch.setattr(enrich, "publication_dates", boom)
    rc = run_enrich(
        monkeypatch,
        tmp_path,
        [
            "--mirror",
            str(m),
            "--diff",
            str(tmp_path / "x.json"),
            "--include-unenriched",
        ],
    )
    assert rc == 2 and m.read_text() == before


def test_enrich_nothing_selected_is_a_noop(monkeypatch, tmp_path):
    m = mirror_file(tmp_path, [{"tik_num": "1", "status": "הבקשה נסגרה"}])
    before = m.read_text()
    assert (
        run_enrich(
            monkeypatch,
            tmp_path,
            ["--mirror", str(m), "--diff", str(tmp_path / "x.json")],
        )
        == 0
    )
    assert m.read_text() == before


def test_enrich_uses_diff_file_and_respects_offset_limit(monkeypatch, tmp_path):
    rows = [{"tik_num": str(i), "status": "נפתח תיק רישוי"} for i in range(1, 6)]
    m = mirror_file(tmp_path, rows)
    d = tmp_path / "diff.json"
    d.write_text(json.dumps({"new_tiks": ["1", "2"], "changed_tiks": ["3", "4", "5"]}))
    fetched = []
    monkeypatch.setattr(
        enrich, "publication_dates", lambda t: fetched.append(t) or ("x", "y")
    )
    run_enrich(
        monkeypatch,
        tmp_path,
        ["--mirror", str(m), "--diff", str(d), "--offset", "1", "--limit", "2"],
    )
    assert fetched == ["2", "3"]


def test_enrich_survives_single_fetch_failure(monkeypatch, tmp_path):
    m = mirror_file(
        tmp_path,
        [
            {"tik_num": "1", "status": "נפתח תיק רישוי"},
            {"tik_num": "2", "status": "נפתח תיק רישוי"},
        ],
    )

    def pd(t):
        if t == "1":
            raise ValueError("bad row")
        return ("2026-01-01", "")

    monkeypatch.setattr(enrich, "publication_dates", pd)
    monkeypatch.setattr(enrich, "call", lambda *a: [])
    assert (
        run_enrich(
            monkeypatch,
            tmp_path,
            ["--mirror", str(m), "--diff", str(tmp_path / "x"), "--include-unenriched"],
        )
        == 0
    )
    out = {r["tik_num"]: r for r in json.loads(m.read_text())["requests"]}
    assert (
        out["2"]["publication_start"] == "2026-01-01"
        and "publication_start" not in out["1"]
    )
    # the failed tik is queued for retry (issue #492)
    assert json.loads((tmp_path / "pending.json").read_text())["pending"] == ["1"]
