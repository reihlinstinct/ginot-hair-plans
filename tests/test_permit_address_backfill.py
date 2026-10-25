"""Issue #452: targeted backfill of raw permit address fields. No network -
address_of is always faked."""
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


def _run(tmp_path, rows, fake, extra_args=()):
    data = _write_data(tmp_path, rows)
    cp = str(tmp_path / "checkpoint.json")
    bf.address_of = fake
    bf.time.sleep = lambda *_: None
    argv = sys.argv
    sys.argv = ["bf", "--data", data, "--checkpoint-file", cp, *extra_args]
    try:
        rc = bf.main()
    finally:
        sys.argv = argv
    out = json.loads(pathlib.Path(data).read_text(encoding="utf-8"))
    return rc, out, cp


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
    bf.apply_fields(r, {"rehovName": "הפלמ״ח", "mispBait": "41", "schunaName": "קטמון"})
    assert r["rehovName"] == "הפלמ״ח" and r["mispBait"] == "41"
    assert r["address"] == "הפלמ״ח 41"
    r2 = _row("2", address="קטמון הישנה")
    bf.apply_fields(r2, {"rehovName": "", "mispBait": "", "schunaName": "קטמון הישנה"})
    assert r2["address"] == ""  # a neighborhood is not an address (#408)


def test_apply_fields_empty_source_invents_nothing():
    r = _row("1", address="קטמון הישנה")
    bf.apply_fields(r, {"rehovName": "", "mispBait": "", "schunaName": ""})
    assert r["address"] == ""
    assert all(r[f] == "" for f in bf.RAW_FIELDS)


def test_main_enriches_and_resumes(tmp_path):
    rows = [
        _row("a", address=""),
        _row("b", address="גוננים"),
        _row("c", address="הפלמ״ח 41"),  # skipped: real street address
    ]
    calls = []

    def fake(tik):
        calls.append(tik)
        return {"rehovName": "הפלמ״ח", "mispBait": "41", "schunaName": "קטמון"}

    rc, out, _cp = _run(tmp_path, rows, fake)
    assert rc == 0
    assert calls == ["a", "b"]
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert enriched["a"]["rehovName"] == "הפלמ״ח"
    assert enriched["a"]["address"] == "הפלמ״ח 41"
    assert enriched["c"]["address"] == "הפלמ״ח 41" and "rehovName" not in enriched["c"]
    # resume: everything already done, no new source calls
    calls.clear()
    rc2, _, _ = _run(tmp_path, out["requests"], fake, extra_args=["--resume"])
    assert rc2 == 0 and calls == []


def test_main_challenge_stops_with_2_and_keeps_progress(tmp_path):
    rows = [_row("a", address=""), _row("b", address=""), _row("c", address="")]

    def fake(tik):
        if tik == "b":
            raise RuntimeError("anti_bot_challenge")
        return {"rehovName": "", "mispBait": "", "schunaName": "גוננים"}

    rc, out, cp = _run(tmp_path, rows, fake)
    assert rc == 2
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert enriched["a"]["schunaName"] == "גוננים"  # flushed before the stop
    assert "rehovName" not in enriched["c"]  # never reached
    done = json.loads(pathlib.Path(cp).read_text(encoding="utf-8"))["done"]
    assert done == ["a"]


def test_main_single_failure_is_not_fatal(tmp_path):
    rows = [_row("a", address=""), _row("b", address="")]

    def fake(tik):
        if tik == "a":
            raise ValueError("garbage response")
        return {"rehovName": "", "mispBait": "", "schunaName": "גוננים"}

    rc, out, _ = _run(tmp_path, rows, fake)
    assert rc == 0
    enriched = {r["tik_num"]: r for r in out["requests"]}
    assert "rehovName" not in enriched["a"]
    assert enriched["b"]["schunaName"] == "גוננים"


def test_dry_run_counts_without_calling_source(tmp_path, capsys):
    rows = [
        _row("a", address=""),
        _row("b", address="גוננים"),
        _row("c", address="הפלמ״ח 41"),
        _row("d", raw=True),
    ]

    def fake(tik):
        raise AssertionError("dry run must not call the source")

    rc, _, _ = _run(tmp_path, rows, fake, extra_args=["--dry-run"])
    assert rc == 0
    text = capsys.readouterr().out
    assert "empty address 1" in text
    assert "no house number 1" in text
    assert "backfill targets 2" in text
