"""Pipeline tests for the permit feed, the enrich step and the mirror ingest.

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


# ---------- permit_feed ----------

def test_ddmmyyyy_parses_and_rejects():
    assert feed.ddmmyyyy("04/10/2026") == "2026-10-04"
    assert feed.ddmmyyyy(" 4/1/2026 ") == "2026-01-04"
    for bad in ("", None, "2026-10-04", "31/13", "a/b/c"):
        assert feed.ddmmyyyy(bad) == ""


def steps(*rows):
    return [{"stepCodeText": s, "execDateStr": e, "planDateStr": p} for s, e, p in rows]


def test_publication_dates_prefers_exec_over_plan(monkeypatch):
    rows = steps((feed.PUB_START_STEP, "01/02/2026", "05/02/2026"),
                 (feed.PUB_END_STEP, "", "20/02/2026"),
                 ("other step", "01/01/2026", ""))
    monkeypatch.setattr(feed, "call", lambda *a: rows)
    assert feed.publication_dates("1/1") == ("2026-02-01", "2026-02-20")


@pytest.mark.parametrize("payload", [None, {}, "x", []])
def test_publication_dates_tolerates_odd_payloads(monkeypatch, payload):
    monkeypatch.setattr(feed, "call", lambda *a: payload)
    assert feed.publication_dates("1/1") == ("", "")


def test_address_of_joins_parts_and_handles_empty(monkeypatch):
    monkeypatch.setattr(feed, "call", lambda *a: [{"rehovName": "אלפסי", "mispBait": 9, "schunaName": ""}])
    assert feed.address_of("1/1") == "אלפסי 9"
    monkeypatch.setattr(feed, "call", lambda *a: None)
    assert feed.address_of("1/1") == ""


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


@pytest.mark.parametrize("marker", [b"<script src=incapsula>", b"Please solve the reCAPTCHA", b"px-captcha"])
def test_call_stops_on_challenge(monkeypatch, marker):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(marker))
    with pytest.raises(RuntimeError):
        feed.call(1, {})


def test_call_access_denied(monkeypatch):
    monkeypatch.setattr(feed.subprocess, "run", fake_curl(b"Access Denied"))
    with pytest.raises(PermissionError):
        feed.call(1, {})


def parcels_file(tmp_path, pairs):
    gj = {"features": [{"properties": {"gush": g, "helka": h}} for g, h in pairs]
          + [{"properties": {"gush": None, "helka": 3}}]}
    p = tmp_path / "parcels.geojson"
    p.write_text(json.dumps(gj))
    return p


def search_row(tik, status="הוכנה טיוטת היתר בניה"):
    return {"tik_num": tik, "mahut_bakasha": " בקשה ", "teurSugbakasha": "היתר",
            "teurStatus": status, "taarih_status": "02/03/2026"}


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

    rc = run_feed(monkeypatch, tmp_path,
                  ["--parcels", str(parcels), "--out", str(out), "--limit", "2"], call)
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
    run_feed(monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call)
    row = json.loads(out.read_text())["requests"][0]
    assert row["status"] == "fresh"


def test_feed_main_stops_on_challenge_without_writing(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"

    def call(*a):
        raise RuntimeError("anti_bot_challenge")

    assert run_feed(monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call) == 2
    assert not out.exists()


def test_feed_main_aborts_after_repeated_failures(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, h) for h in range(1, 10)])
    out = tmp_path / "out.json"
    rc = run_feed(monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out), "--limit", "9"],
                  lambda *a: None)
    assert rc == 1 and not out.exists()


def test_feed_main_keeps_alfasi_parcel_in_every_batch(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1), (100, 2), (30025, 126)])
    seen = []

    def call(proc, params):
        if proc == 242700437:
            seen.append((params["gush"], params["helka"]))
        return []

    run_feed(monkeypatch, tmp_path,
             ["--parcels", str(parcels), "--out", str(tmp_path / "o.json"), "--limit", "1"], call)
    assert (30025, 126) in seen and (100, 1) in seen


def test_feed_detail_failure_is_not_fatal(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"

    def call(proc, params):
        if proc == 242700437:
            return [search_row("T/1")]
        raise ValueError("boom")

    assert run_feed(monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call) == 0
    assert json.loads(out.read_text())["requests"][0]["tik_num"] == "T/1"


# ---------- permit_enrich ----------

def mirror_file(tmp_path, rows):
    p = tmp_path / "mirror.json"
    p.write_text(json.dumps({"requests": rows}, ensure_ascii=False))
    return p


def run_enrich(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(enrich, "SPOTCHECK", str(tmp_path / "spot.json"))
    monkeypatch.setattr(sys, "argv", ["permit_enrich.py"] + argv)
    return enrich.main()


def test_enrich_writes_dates_and_spotcheck(monkeypatch, tmp_path):
    rows = [{"tik_num": "1", "status": "נפתח תיק רישוי"},
            {"tik_num": "2", "status": "נפתח תיק רישוי"},
            {"tik_num": "3", "status": "הבקשה נסגרה"}]
    m = mirror_file(tmp_path, rows)
    monkeypatch.setattr(enrich, "publication_dates",
                        lambda t: ("2026-02-01", "2026-02-20") if t == "1" else ("", ""))
    monkeypatch.setattr(enrich, "call", lambda *a: steps(("שלב", "", "01/01/2026")))
    rc = run_enrich(monkeypatch, tmp_path, ["--mirror", str(m), "--diff", str(tmp_path / "none.json"),
                                            "--include-unenriched"])
    assert rc == 0
    out = {r["tik_num"]: r for r in json.loads(m.read_text())["requests"]}
    assert out["1"]["publication_start"] == "2026-02-01"
    assert out["2"]["publication_start"] == ""
    assert "publication_start" not in out["3"]  # terminal status never fetched
    spot = json.loads((tmp_path / "spot.json").read_text())["samples"]
    assert [s["tik_num"] for s in spot] == ["2"]
    assert spot[0]["steps"] == [{"step": "שלב", "has_exec_date": False, "has_plan_date": True}]


def test_enrich_stops_on_challenge_and_keeps_mirror_untouched(monkeypatch, tmp_path):
    m = mirror_file(tmp_path, [{"tik_num": "1", "status": "נפתח תיק רישוי"}])
    before = m.read_text()

    def boom(t):
        raise RuntimeError("anti_bot_challenge")

    monkeypatch.setattr(enrich, "publication_dates", boom)
    rc = run_enrich(monkeypatch, tmp_path, ["--mirror", str(m), "--diff", str(tmp_path / "x.json"),
                                            "--include-unenriched"])
    assert rc == 2 and m.read_text() == before


def test_enrich_nothing_selected_is_a_noop(monkeypatch, tmp_path):
    m = mirror_file(tmp_path, [{"tik_num": "1", "status": "הבקשה נסגרה"}])
    before = m.read_text()
    assert run_enrich(monkeypatch, tmp_path, ["--mirror", str(m), "--diff", str(tmp_path / "x.json")]) == 0
    assert m.read_text() == before


def test_enrich_uses_diff_file_and_respects_offset_limit(monkeypatch, tmp_path):
    rows = [{"tik_num": str(i), "status": "נפתח תיק רישוי"} for i in range(1, 6)]
    m = mirror_file(tmp_path, rows)
    d = tmp_path / "diff.json"
    d.write_text(json.dumps({"new_tiks": ["1", "2"], "changed_tiks": ["3", "4", "5"]}))
    fetched = []
    monkeypatch.setattr(enrich, "publication_dates", lambda t: fetched.append(t) or ("x", "y"))
    run_enrich(monkeypatch, tmp_path, ["--mirror", str(m), "--diff", str(d), "--offset", "1", "--limit", "2"])
    assert fetched == ["2", "3"]


def test_enrich_survives_single_fetch_failure(monkeypatch, tmp_path):
    m = mirror_file(tmp_path, [{"tik_num": "1", "status": "נפתח תיק רישוי"},
                               {"tik_num": "2", "status": "נפתח תיק רישוי"}])

    def pd(t):
        if t == "1":
            raise ValueError("bad row")
        return ("2026-01-01", "")

    monkeypatch.setattr(enrich, "publication_dates", pd)
    monkeypatch.setattr(enrich, "call", lambda *a: [])
    assert run_enrich(monkeypatch, tmp_path, ["--mirror", str(m), "--diff", str(tmp_path / "x"),
                                              "--include-unenriched"]) == 0
    out = {r["tik_num"]: r for r in json.loads(m.read_text())["requests"]}
    assert out["2"]["publication_start"] == "2026-01-01" and "publication_start" not in out["1"]


# ---------- mirror_ingest ----------

def test_parcel_interval_edge_cases():
    assert mirror.parcel_interval({"מחלקה": "22", "עד חלקה": "5032"}) == (set(), (22, 5032))
    assert mirror.parcel_interval({"מחלקה": "216", "עד חלקה": "2"}) == ({216, 2}, None)
    assert mirror.parcel_interval({"מחלקה": "7"}) == (set(), (7, 7))
    assert mirror.parcel_interval({"מחלקה": "x"}) == (set(), None)


def test_matching_parcels_interval_and_points():
    by_gush = {100: {1, 5, 9}}
    assert mirror.matching_parcels({"גוש": "100", "מחלקה": "4", "עד חלקה": "9"}, by_gush) == (100, [5, 9])
    assert mirror.matching_parcels({"גוש": "100", "מחלקה": "9", "עד חלקה": "1"}, by_gush) == (100, [1, 9])
    assert mirror.matching_parcels({"גוש": "999", "מחלקה": "1"}, by_gush) == (999, [])
    assert mirror.matching_parcels({"גוש": "abc"}, by_gush) == (0, [])


def test_map_record_never_reads_personal_column():
    row = {"מספר תיק": " 1/2 ", "סטטוס": "ס", "תאריך סטטוס": "2026-01-02T00:00:00", "רחוב": "אלפסי",
           "מספר בית": "0", "שכונה": "טלביה", "בעלי עניין": "שם פרטי"}
    rec = mirror.map_record(row, 30025, [126])
    assert rec["tik_num"] == "1/2" and rec["status_date"] == "2026-01-02"
    assert rec["address"] == "אלפסי טלביה"  # house number 0 dropped
    assert "שם פרטי" not in json.dumps(rec, ensure_ascii=False)


def test_diff_records_new_changed_gone():
    old = [{"tik_num": "a", "status": "x", "status_date": "1"},
           {"tik_num": "b", "status": "x", "status_date": "1"},
           {"tik_num": "c", "status": "x", "status_date": "1"}]
    new = [{"tik_num": "a", "status": "x", "status_date": "1"},
           {"tik_num": "b", "status": "y", "status_date": "1"},
           {"tik_num": "d", "status": "x", "status_date": "1"}]
    assert mirror.diff_records(old, new) == {"new_tiks": ["d"], "changed_tiks": ["b"], "gone_tiks": ["c"]}


def test_fetch_rows_pages_until_total(monkeypatch):
    monkeypatch.setattr(mirror, "PAGE", 2)
    pages = [{"success": True, "result": {"records": [{"i": 1}, {"i": 2}], "total": 3}},
             {"success": True, "result": {"records": [{"i": 3}], "total": 3}}]
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, json.dumps(pages[len(calls) - 1]), "")

    monkeypatch.setattr(mirror.subprocess, "run", run)
    assert [r["i"] for r in mirror.fetch_rows([100])] == [1, 2, 3]
    assert len(calls) == 2 and "offset=2" in calls[1]


def test_fetch_rows_raises_on_api_error(monkeypatch):
    monkeypatch.setattr(mirror.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '{"success": false}', ""))
    with pytest.raises(RuntimeError):
        mirror.fetch_rows([1])


def test_mirror_main_end_to_end(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 5)])
    out, diff = tmp_path / "m.json", tmp_path / "d.json"
    out.write_text(json.dumps({"requests": [{"tik_num": "gone", "status": "x", "status_date": ""}]}))
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps({"requests": [{"tik_num": "T/1"}, {"tik_num": "only-direct"}]}))
    rows = [
        {"מספר תיק": "T/1", "גוש": "100", "מחלקה": "5", "עד חלקה": "5", "סטטוס": "ס", "בעלי עניין": "סודי"},
        {"מספר תיק": "T/2", "גוש": "100", "מחלקה": "50", "עד חלקה": "50"},   # not a council parcel
        {"מספר תיק": "", "גוש": "100", "מחלקה": "5"},                      # no tik number
    ]
    monkeypatch.setattr(mirror, "fetch_rows", lambda g: rows)
    monkeypatch.setattr(sys, "argv", ["m", "--parcels", str(parcels), "--out", str(out),
                                      "--diff-out", str(diff), "--validate-against", str(direct)])
    assert mirror.main() == 0
    data = json.loads(out.read_text())
    assert [r["tik_num"] for r in data["requests"]] == ["T/1"]
    assert "סודי" not in out.read_text()
    assert "DRAFT" in data["label"]
    d = json.loads(diff.read_text())
    assert d["new_tiks"] == ["T/1"] and d["gone_tiks"] == ["gone"]
    v = mirror.validate({"T/1": {}}, str(direct))
    assert v["common"] == 1 and v["direct_only"] == ["only-direct"]


def test_checkpoint_large_payload_uses_stdin_not_argv(monkeypatch):
    payload = {"content": "x" * 300000}
    seen = {}
    def run(cmd, **kwargs):
        seen.update(cmd=cmd, kwargs=kwargs)
        return subprocess.CompletedProcess(cmd, 0, '{"commit": {"sha": "ok"}}', '')
    monkeypatch.setattr(feed.subprocess, "run", run)
    assert feed.gh_api("PUT", "/repos/test/test/contents/data.json", "test", payload)["commit"]
    assert "@-" in seen["cmd"]
    assert max(map(len, seen["cmd"])) < 1000
    assert json.loads(seen["kwargs"]["input"]) == payload


@pytest.mark.parametrize("age,status,complete,reuse", [
    ("today", "fresh", True, True),
    ("2000-01-01", "fresh", True, False),
    ("today", "old", True, False),
    ("today", "fresh", False, False),
    (None, "fresh", True, False),
])
def test_feed_reuses_only_complete_same_day_unchanged_details(monkeypatch, tmp_path, age, status, complete, reuse):
    parcels = parcels_file(tmp_path, [(100, 1)])
    out = tmp_path / "out.json"
    prior = {"tik_num": "T/1", "mahut": "בקשה", "sugbakasha": "היתר", "status": status,
             "status_date": "2026-03-02", "publication_start": "2026-02-01",
             "publication_end_planned": "", "address": "cached"}
    if age:
        prior["details_checked_on"] = feed.datetime.date.today().isoformat() if age == "today" else age
    if not complete:
        del prior["address"]
    out.write_text(json.dumps({"requests": [prior]}))
    seen = []
    def call(proc, params):
        seen.append(proc)
        return [search_row("T/1", "fresh")] if proc == 242700437 else []
    assert run_feed(monkeypatch, tmp_path, ["--parcels", str(parcels), "--out", str(out)], call) == 0
    assert (242700451 not in seen) == reuse
    row = json.loads(out.read_text())["requests"][0]
    assert row["details_checked_on"] == feed.datetime.date.today().isoformat()
    assert row["address"] == ("cached" if reuse else "")
