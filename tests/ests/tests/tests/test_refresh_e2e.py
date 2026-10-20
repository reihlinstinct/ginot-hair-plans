"""End-to-end: refresh.py on synthetic iplan features -> every public artifact.

iplan (network) is stubbed with fixed features; everything after it runs for
real: rows, CSV/XLSX, plan.json files, snapshot diff, site, feed, badges.
Also covers iplan.query_plans (curl stubbed) and the DXF reader.
"""
import csv
import datetime
import json
import pathlib
import subprocess
import sys

import ezdxf
import openpyxl
import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import refresh
from ginot import dwg, iplan, tracking

MS_DAY = 86400 * 1000
BASE_MS = int(datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def feat(num, status, **kw):
    attrs = {"pl_number": num, "pl_name": f"תכנית {num}", "station_desc": status,
             "receiving_date": BASE_MS, "pl_area_dunam": 2.5,
             "pl_url": f"https://mavat.iplan.gov.il/{num}"}
    attrs.update(kw)
    return {"attributes": attrs, "geometry": None}


FEATURES = [
    feat("101-1", "הפקדה להתנגדויות", pl_date_advertise=BASE_MS + 5 * MS_DAY),
    feat("101-2", "אישור"),
    feat("101-3", "בדיקה תכנונית"),
]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    council = ROOT / "data" / "council_ginot_hair.geojson"
    (tmp_path / "data" / "council.geojson").write_text(council.read_text(encoding="utf-8"), encoding="utf-8")
    state = {"features": list(FEATURES)}
    monkeypatch.setattr(refresh.iplan, "query_plans",
                        lambda council, service="x", **kw: state["features"] if service == "xplan_without_77_78"
                        else [{"attributes": {"pl_number": "77-1", "pl_name": "ס77", "station_desc": "x", "pl_url": "u"}}])
    return tmp_path, state


def run_refresh(monkeypatch, tmp):
    monkeypatch.setattr(sys, "argv", ["refresh.py", "--council", "data/council.geojson",
                                      "--out", "out", "--site", "docs", "--snapshots", "snapshots",
                                      "--status", "data/plan_status.json"])
    refresh.main()


def test_full_refresh_produces_all_public_artifacts(workdir, monkeypatch):
    tmp, _ = workdir
    run_refresh(monkeypatch, tmp)
    rows = list(csv.DictReader((tmp / "out" / "ginot_hair_plans.csv").open(encoding="utf-8-sig")))
    assert sorted(r["pl_number"] for r in rows) == ["101-1", "101-2", "101-3"]
    dep = next(r for r in rows if r["pl_number"] == "101-1")
    assert dep["objection_deadline_derived_60d_from_publication"] == "2026-12-05"  # Oct 6 + 60d
    ws = openpyxl.load_workbook(tmp / "out" / "ginot_hair_plans.xlsx").active
    assert ws.max_row == 4  # header + 3
    assert json.loads((tmp / "plans" / "101-1" / "plan.json").read_text(encoding="utf-8"))["pl_number"] == "101-1"
    html = (tmp / "docs" / "index.html").read_text(encoding="utf-8")
    assert "תכנית 101-1" in html and "<table" in html
    data = json.loads((tmp / "docs" / "data.json").read_text(encoding="utf-8"))
    assert len(data["rows"]) == 3 and data["permits"] == []
    assert "<feed" in (tmp / "docs" / "feed.xml").read_text(encoding="utf-8")
    assert json.loads((tmp / "docs" / "badge" / "plans.json").read_text())["message"] == "3"
    badges = {p.name for p in (tmp / "docs" / "badge").glob("status_*.json")}
    assert {"status_deposit.json", "status_approved.json", "status_review.json"} <= badges
    snap = json.loads((tmp / "snapshots" / "latest.json").read_text(encoding="utf-8"))
    assert len(snap["rows"]) == 3 and snap["plans_77_78"][0]["pl_number"] == "77-1"


def test_second_refresh_reports_only_real_changes(workdir, monkeypatch):
    tmp, state = workdir
    run_refresh(monkeypatch, tmp)
    state["features"] = [FEATURES[0], feat("101-2", "בדיקה תכנונית"), FEATURES[2], feat("101-4", "בדיקה תכנונית")]
    run_refresh(monkeypatch, tmp)
    changes = json.loads((tmp / "out" / "changes.json").read_text(encoding="utf-8"))["changes"]
    kinds = {(c["pl_number"], c["kind"]) for c in changes}
    assert ("101-4", "new") in kinds
    assert not any(c["pl_number"] == "101-3" for c in changes)  # unchanged plan is silent
    assert any(c["pl_number"] == "101-2" for c in changes)       # status moved


def test_planner_tracking_never_reaches_public_files(workdir, monkeypatch):
    tmp, _ = workdir
    tracking.save({"101-1": {"state": "objection_filed", "updated": "2026-10-02", "note": "SECRET-NOTE"}},
                  str(tmp / "data" / "plan_status.json"))
    run_refresh(monkeypatch, tmp)
    blob = ""
    for p in list((tmp / "docs").rglob("*")) + list((tmp / "out").rglob("*.csv")) + list((tmp / "plans").rglob("*.json")) \
            + list((tmp / "snapshots").rglob("*.json")):
        if p.is_file():
            blob += p.read_text(encoding="utf-8", errors="ignore")
    assert "SECRET-NOTE" not in blob and "objection_filed" not in blob and "tracking_state" not in blob


def test_permits_file_is_rendered_when_present(workdir, monkeypatch):
    tmp, _ = workdir
    (tmp / "data" / "permit_requests.json").write_text(json.dumps({"requests": [
        {"tik_num": "1993/0664.03", "status": "הבקשה נסגרה", "mahut": "m", "sugbakasha": "s",
         "gush": 1, "helka": 2, "address": "אלפסי 9", "publication_start": "", "publication_end_planned": ""}]},
        ensure_ascii=False), encoding="utf-8")
    run_refresh(monkeypatch, tmp)
    data = json.loads((tmp / "docs" / "data.json").read_text(encoding="utf-8"))
    assert data["permits"][0]["tik_num"] == "1993/0664.03"
    assert "1993/0664.03" in (tmp / "docs" / "index.html").read_text(encoding="utf-8")


def test_land_status_recomputes_deadline_from_latest_publication(tmp_path):
    land = tmp_path / "land.json"
    land.write_text(json.dumps({"plans": {"P1": {"land_status": "הפקדה", "land_status_date": "2026-11-10",
                                                 "land_plan_id": 7, "is_deposit_publication": True},
                                          "P2": {"land_status": "x", "land_status_date": "2027-01-01",
                                                 "is_deposit_publication": False}}}), encoding="utf-8")
    rows = [{"pl_number": "P1", "pl_date_advertise": "2026-10-01",
             "objection_deadline_derived_60d_from_publication": "2026-11-30"},
            {"pl_number": "P2", "pl_date_advertise": "2026-10-01",
             "objection_deadline_derived_60d_from_publication": "2026-11-30"},
            {"pl_number": "P3"}]
    out = refresh.merge_land_status(rows, str(land))
    assert out[0]["objection_deadline_derived_60d_from_publication"] == "2027-01-09"  # Nov 10 + 60d
    assert out[1]["objection_deadline_derived_60d_from_publication"] == "2026-11-30"   # not a deposit notice
    assert "land_status" not in out[2]
    assert refresh.merge_land_status(rows, str(tmp_path / "missing.json")) is rows


# ---------- iplan.query_plans (curl stubbed) ----------

def stub_curl(monkeypatch, outputs):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, outputs[min(len(calls), len(outputs)) - 1], "")

    monkeypatch.setattr(iplan.subprocess, "run", run)
    return calls


COUNCIL = refresh.load_council(str(ROOT / "data" / "council_ginot_hair.geojson"))


def test_query_plans_returns_features(monkeypatch):
    calls = stub_curl(monkeypatch, [json.dumps({"features": [{"attributes": {"pl_number": "1"}}]})])
    assert iplan.query_plans(COUNCIL)[0]["attributes"]["pl_number"] == "1"
    assert any("returnGeometry=true" in c for c in calls[0])
    assert "Xplan_77_78" in iplan.BASE + "/Xplan_77_78" and len(calls) == 1


def test_query_plans_retries_with_legacy_tls_on_bad_json(monkeypatch):
    calls = stub_curl(monkeypatch, ["<html>handshake</html>", json.dumps({"features": []})])
    assert iplan.query_plans(COUNCIL, return_geometry=False) == []
    assert len(calls) == 2 and "--tlsv1.0" in calls[1]


def test_query_plans_raises_on_arcgis_error(monkeypatch):
    stub_curl(monkeypatch, [json.dumps({"error": {"code": 400}})])
    with pytest.raises(RuntimeError):
        iplan.query_plans(COUNCIL)


# ---------- dwg ----------

def make_dxf(path):
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
    msp.add_lwpolyline([(0, 0), (5, 5), (9, 1)], close=False)   # open: ignored
    msp.add_lwpolyline([(0, 0), (1, 1), (2, 0)], close=True)    # < 4 points: ignored
    doc.saveas(path)


def test_read_polygons_only_closed_polylines(tmp_path):
    p = tmp_path / "a.dxf"
    make_dxf(str(p))
    polys = dwg.read_polygons(str(p))
    assert len(polys) == 1 and polys[0].area == 100


def test_repair_dxf_wkt_rejoins_split_line(tmp_path):
    src = tmp_path / "in.dxf"
    src.write_text('x\nPROJCS["Israel_TM_Grid",GEOGCS[\n"GCS"]]\ny\n', encoding="utf-8")
    out = dwg.repair_dxf_wkt(str(src), str(tmp_path / "out.dxf"))
    text = pathlib.Path(out).read_text(encoding="utf-8")
    assert 'PROJCS["Israel_TM_Grid",GEOGCS["GCS"]]' in text and text.count("\n") == 3


def test_convert_dwg_to_dxf_calls_tool(monkeypatch):
    seen = []
    monkeypatch.setattr(dwg.subprocess, "run", lambda cmd, **kw: seen.append(cmd))
    assert dwg.convert_dwg_to_dxf("a.dwg", "a.dxf", dwg2dxf="tool") == "a.dxf"
    assert seen == [["tool", "-o", "a.dxf", "a.dwg"]]
