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


def parcels_file(tmp_path, pairs):
    gj = {
        "features": [{"properties": {"gush": g, "helka": h}} for g, h in pairs]
        + [{"properties": {"gush": None, "helka": 3}}]
    }
    p = tmp_path / "parcels.geojson"
    p.write_text(json.dumps(gj))
    return p


# Section: Mirror ingest and privacy


def test_parcel_interval_edge_cases():
    assert mirror.parcel_interval({"מחלקה": "22", "עד חלקה": "5032"}) == (
        set(),
        (22, 5032),
    )
    assert mirror.parcel_interval({"מחלקה": "216", "עד חלקה": "2"}) == ({216, 2}, None)
    assert mirror.parcel_interval({"מחלקה": "7"}) == (set(), (7, 7))
    assert mirror.parcel_interval({"מחלקה": "x"}) == (set(), None)


def test_matching_parcels_interval_and_points():
    by_gush = {100: {1, 5, 9}}
    assert mirror.matching_parcels(
        {"גוש": "100", "מחלקה": "4", "עד חלקה": "9"}, by_gush
    ) == (100, [5, 9])
    assert mirror.matching_parcels(
        {"גוש": "100", "מחלקה": "9", "עד חלקה": "1"}, by_gush
    ) == (100, [1, 9])
    assert mirror.matching_parcels({"גוש": "999", "מחלקה": "1"}, by_gush) == (999, [])
    assert mirror.matching_parcels({"גוש": "abc"}, by_gush) == (0, [])


def test_map_record_never_reads_personal_column():
    row = {
        "מספר תיק": " 1/2 ",
        "סטטוס": "ס",
        "תאריך סטטוס": "2026-01-02T00:00:00",
        "רחוב": "אלפסי",
        "מספר בית": "0",
        "שכונה": "טלביה",
        "בעלי עניין": "שם פרטי",
    }
    rec = mirror.map_record(row, 30025, [126])
    assert rec["tik_num"] == "1/2" and rec["status_date"] == "2026-01-02"
    assert rec["address"] == "אלפסי טלביה"  # house number 0 dropped
    assert "שם פרטי" not in json.dumps(rec, ensure_ascii=False)


def test_diff_records_new_changed_gone():
    old = [
        {"tik_num": "a", "status": "x", "status_date": "1"},
        {"tik_num": "b", "status": "x", "status_date": "1"},
        {"tik_num": "c", "status": "x", "status_date": "1"},
    ]
    new = [
        {"tik_num": "a", "status": "x", "status_date": "1"},
        {"tik_num": "b", "status": "y", "status_date": "1"},
        {"tik_num": "d", "status": "x", "status_date": "1"},
    ]
    assert mirror.diff_records(old, new) == {
        "new_tiks": ["d"],
        "changed_tiks": ["b"],
        "gone_tiks": ["c"],
    }


def test_fetch_rows_pages_until_total(monkeypatch):
    monkeypatch.setattr(mirror, "PAGE", 2)
    pages = [
        {
            "success": True,
            "result": {
                "records": [{"i": 1, "מספר תיק": "1"}, {"i": 2, "מספר תיק": "2"}],
                "total": 3,
            },
        },
        {
            "success": True,
            "result": {"records": [{"i": 3, "מספר תיק": "3"}], "total": 3},
        },
    ]
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[-1])
        return subprocess.CompletedProcess(
            cmd, 0, json.dumps(pages[len(calls) - 1]), ""
        )

    monkeypatch.setattr(mirror.subprocess, "run", run)
    assert [r["i"] for r in mirror.fetch_rows([100])] == [1, 2, 3]
    assert len(calls) == 2 and "offset=2" in calls[1]


def test_fetch_rows_raises_on_api_error(monkeypatch):
    monkeypatch.setattr(
        mirror.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, '{"success": false}', ""),
    )
    with pytest.raises(RuntimeError):
        mirror.fetch_rows([1])


def test_mirror_main_end_to_end(monkeypatch, tmp_path):
    parcels = parcels_file(tmp_path, [(100, 5)])
    out, diff = tmp_path / "m.json", tmp_path / "d.json"
    out.write_text(
        json.dumps(
            {"requests": [{"tik_num": "gone", "status": "x", "status_date": ""}]}
        )
    )
    direct = tmp_path / "direct.json"
    direct.write_text(
        json.dumps({"requests": [{"tik_num": "T/1"}, {"tik_num": "only-direct"}]})
    )
    rows = [
        {
            "מספר תיק": "T/1",
            "גוש": "100",
            "מחלקה": "5",
            "עד חלקה": "5",
            "סטטוס": "ס",
            "בעלי עניין": "סודי",
        },
        {
            "מספר תיק": "T/2",
            "גוש": "100",
            "מחלקה": "50",
            "עד חלקה": "50",
        },  # not a council parcel
        {"מספר תיק": "", "גוש": "100", "מחלקה": "5"},  # no tik number
    ]
    monkeypatch.setattr(mirror, "fetch_rows", lambda g: rows)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "m",
            "--parcels",
            str(parcels),
            "--out",
            str(out),
            "--diff-out",
            str(diff),
            "--validate-against",
            str(direct),
        ],
    )
    assert mirror.main() == 0
    data = json.loads(out.read_text())
    assert [r["tik_num"] for r in data["requests"]] == ["T/1"]
    assert "סודי" not in out.read_text()
    assert "DRAFT" in data["label"]
    d = json.loads(diff.read_text())
    assert d["new_tiks"] == ["T/1"] and d["gone_tiks"] == ["gone"]
    v = mirror.validate({"T/1": {}}, str(direct))
    assert v["common"] == 1 and v["direct_only"] == ["only-direct"]
