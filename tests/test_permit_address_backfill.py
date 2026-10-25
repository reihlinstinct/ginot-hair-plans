"""Issue #452: targeted backfill of raw permit address fields. No network -
address_fields_strict is always faked, and test doubles are installed with
monkeypatch so nothing leaks into the shared process (review finding)."""
import importlib.util
import json
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location(
    "permit_address_backfill", vpn / "permit_address_backfill.py"
)
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def _row(tik, address=None, raw=False):
    r = {"tik_num": tik, "status": "בבדיקה", "details_checked_on": "2026-10-24"}
    if address is not None:
        r["address"] = address
    if raw:
        r.update({"rehovName": "הפלמ״ח", "mispBait": "41", "schunaName": "קטמון"})
    return r


def _write_data(tmp_path, rows):
    path = tmp_path / "permit_requests.json"
    path.write_text(
        json.dumps({"generated": "2026-10-25", "requests": rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


def _run(tmp_path, rows, fake, monkeypatch, extra_args=()):
    data = _write_data(tmp_path, rows)
    cp = str(tmp_path / "checkpoint.json")
    monkeypatch.setattr(bf, "address_fields_strict", fake)
    monkeypatch.setattr(bf.time, "sleep", lambda *_: None)
    argv = sys.argv
    monkeypatch.setattr(sys, "argv", ["bf", "--data", data, "--checkpoint-file", cp, *extra_args])
    try:
        rc = bf.main()
    finally:
        sys.argv = argv
    out = json.loads(pathlib.Path(data).read_text(encoding="utf-8"))
    return rc, out, cp


def _fields(street="", num="", schuna=""):
    return {"rehovName": street, "mispBait": num, "schunaName": schuna}


def test_has_house_number():
    assert bf.has_house_number("הפלמ״ח 41")
    assert not bf.has_house_number("קטמון הישנה")
    assert not bf.has_house_number("")


def test_needs_backfill_selection():
    assert bf.needs_backfill(_row("1", address=""))  # empty address
    assert bf.needs_backfill(_row("2", address="קטמון הישנה"))  # no house number
    assert not bf.needs_backfill(_row("3", address="הפלמ״ח 41"))  # real street address
    assert not bf.needs_backfill(_row("4", raw=True))  # raw fields already present
    assert bf.select_targets(
        [_row("1", address=""), _row("2", address="הפלמ״ח 41"), _row("3", address="גוננים")]
    ) == ["1", "3"]


def test_apply_fields_street_and_neighborhood():
    r = _row("1", address="קטמון הישנה")
    bf.apply_fields(r, _fields("הפלמ״ח", "41", "קטמון"))
    assert r["rehovName"] == "הפלמ״ח" and r["mispBait"] == "41"
    assert r["address"] == "הפלמ״ח 41"
    r2 = _row("2", address="קטמון הישנה")
    bf.apply_fields(r2, _fields(schuna="קטמון הישנה"))
    assert r2["address"] == ""  # a neighborhood is not an address (#408)


def test_apply_fields_empty_source_invents_nothing():
    r = _row("1", address="קטמון הישנה")
    bf.apply_fields(r, _fields())
    assert r["address"] == ""
    assert all(r[f] == "" for f in bf.RAW_FIELDS)


def test_strict_fetch_distinguishes_failure_from_empty(monkeypatch):
    """Review finding: a failed/unparseable response (call() -> None) must
    raise - it must never be persisted as 'no address' - while a genuine
    empty list means the source has no row and stores empty fields."""
    monkeypatch.setattr(bf._feed, "call", lambda *a: None)
    try:
        bf.address_fields_strict("2026/0001.01")
        raise AssertionError("None response must raise, not become empty fields")
    except ValueError:
        pass
    for bad in ({"error": "nope"}, "garbage", 42):
        monkeypatch.setattr(bf._feed, "call", lambda *a, _b=bad: _b)
        try:
            bf.address_fields_strict("2026/0001.01")
            raise AssertionError(f"{type(bad).__name__} response must raise, not become empty fields")
        except ValueError:
            pass
    monkeypatch.setattr(bf._feed, "call", lambda *a: ["not-a-dict"])
    try:
        bf.address_fields_strict("2026/0001.01")
        raise AssertionError("non-dict row must raise")
    except ValueError:
        pass
    monkeypatch.setattr(bf._feed, "call", lambda *a: [])
    assert bf.address_fields_strict("2026/0001.01") == _fields()


def test_main_enriches_and_resumes(tmp_path, monkeypatch):
    rows = [
        _row("a", address=""),
        _row("b", address="גוננים"),
        _row("c", address="הפלמ״ח 41"),  # skipped: real street address
    ]
    calls = []

    def fake(tik):
        calls.append(tik)
        return _fields("הפלמ״ח", "41", "קטמון")

    rc, out, _cp = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 0
    assert calls == ["a", "b"]
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert enriched["a"]["rehovName"] == "הפלמ״ח"
    assert enriched["a"]["address"] == "הפלמ״ח 41"
    assert enriched["c"]["address"] == "הפלמ״ח 41" and "rehovName" not in enriched["c"]
    # resume: everything already done, no new source calls
    calls.clear()
    rc2, _, _ = _run(tmp_path, out["requests"], fake, monkeypatch, extra_args=["--resume"])
    assert rc2 == 0 and calls == []


def test_resume_ignores_checkpoint_from_a_replaced_data_file(tmp_path, monkeypatch):
    """Review finding: if the data file is replaced mid-backfill (e.g. a
    weekly refresh lands), the stale checkpoint must not skip re-enrichment."""
    rows = [_row("a", address=""), _row("b", address="")]
    calls = []

    def fake(tik):
        calls.append(tik)
        return _fields(schuna="גוננים")

    rc, _out, _cp = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 0 and calls == ["a", "b"]
    # simulate the refresh replacing the data file (regenerated, raw fields
    # gone, plus one newly scanned row so the content really differs)
    replaced = [_row("a", address=""), _row("b", address=""), _row("z", address="הפלמ״ח 41")]
    calls.clear()
    rc2, _out2, _cp2 = _run(tmp_path, replaced, fake, monkeypatch, extra_args=["--resume"])
    assert rc2 == 0
    assert calls == ["a", "b"]  # re-enriched, not skipped by the stale checkpoint


def test_main_challenge_stops_with_2_and_keeps_progress(tmp_path, monkeypatch):
    rows = [_row("a", address=""), _row("b", address=""), _row("c", address="")]

    def fake(tik):
        if tik == "b":
            raise RuntimeError("anti_bot_challenge")
        return _fields(schuna="גוננים")

    rc, out, cp = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 2
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert enriched["a"]["schunaName"] == "גוננים"  # flushed before the stop
    assert "rehovName" not in enriched["c"]  # never reached
    done = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))["done"]
    assert done == ["a"]


def test_permission_error_stops_with_2_not_a_silent_zero(tmp_path, monkeypatch):
    """Review finding: access denied (PermissionError from the client) is an
    access wall - stop with a non-zero exit, never a run that exits 0 having
    enriched nothing."""
    rows = [_row("a", address=""), _row("b", address="")]

    def fake(tik):
        raise PermissionError("access_denied")

    rc, out, _cp = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 2
    assert all("rehovName" not in r for r in out["requests"])


def test_none_response_keeps_legacy_address_and_allows_retry(tmp_path, monkeypatch):
    """Review finding: a failed response must not clear a good legacy
    address nor mark the tik done - the next run retries it."""
    rows = [_row("a", address="גוננים"), _row("b", address="קריית שמואל")]

    def fake(tik):
        if tik == "a":
            raise ValueError("no usable response")  # what strict() raises on None
        return _fields(schuna="קריית שמואל")

    rc, out, cp = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 1  # one failure below the consecutive threshold: batch not complete
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert enriched["a"]["address"] == "גוננים"  # legacy address NOT cleared
    assert "rehovName" not in enriched["a"]
    done = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))["done"]
    assert done == ["b"]  # the failed tik stays pending for a retry run


def test_consecutive_failures_abort_with_nonzero(tmp_path, monkeypatch):
    """Review finding: a systemic failure (tunnel down) looks like per-tik
    failures - abort after the feed's MAX_CONSECUTIVE_FAILURES, exit != 0."""
    rows = [_row(f"t{i}", address="") for i in range(10)]
    calls = []

    def fake(tik):
        calls.append(tik)
        raise ValueError("no usable response")

    rc, _, _ = _run(tmp_path, rows, fake, monkeypatch)
    assert rc == 1
    assert len(calls) == bf.MAX_CONSECUTIVE_FAILURES  # stopped early, not all 10


def test_sleep_double_does_not_leak_process_wide(tmp_path, monkeypatch):
    """Review finding: tests must not overwrite time.sleep globally - the
    double lives only inside the patch context."""
    real_sleep = bf.time.sleep
    with monkeypatch.context() as m:
        _run(tmp_path, [_row("a", address="")], lambda tik: _fields(), m)
        assert bf.time.sleep is not real_sleep  # double active inside the run
    assert bf.time.sleep is real_sleep  # restored afterwards


def test_dry_run_counts_without_calling_source(tmp_path, capsys, monkeypatch):
    rows = [
        _row("a", address=""),
        _row("b", address="גוננים"),
        _row("c", address="הפלמ״ח 41"),
        _row("d", raw=True),
    ]

    def fake(tik):
        raise AssertionError("dry run must not call the source")

    rc, _, _ = _run(tmp_path, rows, fake, monkeypatch, extra_args=["--dry-run"])
    assert rc == 0
    text = capsys.readouterr().out
    assert "empty address 1" in text
    assert "no house number 1" in text
    assert "backfill targets 2" in text
