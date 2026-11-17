"""Unit tests for the daily active-publications diff (issue #527)."""

import importlib.util
import json
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "rishui_publish_watch_u", ROOT / "scripts/vpn/rishui_publish_watch.py"
)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

IN_ROW = {
    "myIndex": 2,
    "tik_num": "2026/0439.00",
    "street": "הפלמח",
    "house_number": "41",
    "neighborhood": "קטמון הישנה",
    "publication_date": "2026-10-18",
    "objection_deadline": "2026-11-13",
    "in_polygon": True,
}
OUT_ROW = {
    "myIndex": 3,
    "tik_num": "2026/9999.00",
    "neighborhood": "רמות",
    "in_polygon": False,
}
UNRESOLVED_ROW = {
    "myIndex": 4,
    "tik_num": "2026/0001.00",
    "neighborhood": None,
    "in_polygon": None,
}
OLD = [{"myIndex": 1, "neighborhood": "קטמון הישנה", "in_polygon": True}]


def test_seed_writes_baseline_without_alerts():
    baseline, payload, seeded = watch.update(None, [IN_ROW, OUT_ROW])
    assert seeded
    assert baseline == [IN_ROW]  # out-of-polygon row dropped even at seed
    assert payload == {"new_in_polygon": [], "unresolved_new": []}


def test_new_in_polygon_row_is_reported_and_outside_ignored():
    baseline, payload, seeded = watch.update(
        OLD, OLD + [IN_ROW, OUT_ROW, UNRESOLVED_ROW]
    )
    assert not seeded
    assert payload["new_in_polygon"] == [IN_ROW]
    assert payload["unresolved_new"] == [UNRESOLVED_ROW]
    # baseline keeps in-polygon + unresolved, drops out-of-polygon
    assert baseline == OLD + [IN_ROW, UNRESOLVED_ROW]


def test_unresolved_row_not_reflagged_daily():
    baseline, _payload, _ = watch.update(OLD, OLD + [UNRESOLVED_ROW])
    _, payload2, _ = watch.update(baseline, baseline)
    assert payload2 == {"new_in_polygon": [], "unresolved_new": []}


def test_fallback_marker_survives_into_payload_and_baseline():
    new_row = dict(
        UNRESOLVED_ROW,
        in_polygon=True,
        in_polygon_source="publication_point_evidence",
    )
    baseline, payload, seeded = watch.update([dict(UNRESOLVED_ROW)], [new_row])
    assert not seeded
    assert payload["new_in_polygon"] == [new_row]
    assert payload["unresolved_new"] == []
    assert baseline == [new_row]


def test_main_roundtrip(tmp_path):
    new = tmp_path / "new.json"
    new.write_text(json.dumps([IN_ROW, OUT_ROW], ensure_ascii=False), encoding="utf-8")
    permits = tmp_path / "permits.json"
    permits.write_text(
        json.dumps(
            [
                {"tik_num": "2026/0439.00", "gush": 30016, "helka": 87},
                {"tik_num": "2026/9999.00", "gush": 99999, "helka": 1},
            ]
        ),
        encoding="utf-8",
    )
    parcels = tmp_path / "parcels.json"
    parcels.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"gush": 30016, "helka": 87},
                        "geometry": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_active = tmp_path / "active.json"
    out_new = tmp_path / "alert.json"
    rc = watch.main(
        [
            "--old",
            str(tmp_path / "missing.json"),
            "--new",
            str(new),
            "--permits",
            str(permits),
            "--parcels",
            str(parcels),
            "--out-active",
            str(out_active),
            "--out-new",
            str(out_new),
        ]
    )
    assert rc == 0
    # main re-resolves from permits+parcels: IN_ROW in-polygon; OUT_ROW's parcel
    # is outside the polygon parcel set -> dropped
    active = json.loads(out_active.read_text(encoding="utf-8"))
    assert [r["tik_num"] for r in active] == ["2026/0439.00"]
    assert active[0]["in_polygon"] is True
    assert json.loads(out_new.read_text(encoding="utf-8")) == {
        "new_in_polygon": [],
        "unresolved_new": [],
    }


def test_unresolved_row_alerts_when_it_resolves_into_scope():
    """#527: a baseline row with in_polygon=None whose tik later resolves to a
    polygon parcel must alert on the transition, not slip in silently."""
    before = [dict(UNRESOLVED_ROW, in_polygon=None)]
    after = [dict(UNRESOLVED_ROW, in_polygon=True)]
    _, payload, _ = watch.update(before, after)
    assert payload["new_in_polygon"] == [after[0]]
    assert payload["unresolved_new"] == []


def test_watch_workflow_contract():
    """Daily schedule, single fetch through the tunnel, guarded data commit,
    tunnel always torn down (issue #527)."""
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/rishui-publish-watch.yml"
    ).read_text()
    assert "schedule:" in workflow
    assert "workflow_dispatch" in workflow
    assert "scripts/vpn/l2tp.py up" in workflow
    assert "scripts/vpn/rishui_publish.py fetch --out /tmp/publish-new.json" in workflow
    assert "rishui_publish_watch.py" in workflow
    assert "scripts/ci/publish_publications.py" in workflow
    assert "scripts/vpn/l2tp.py down" in workflow


# Section: main() wiring of the official-point fallback (#857)

FALLBACK_ROW = {
    "myIndex": 7,
    "tik_num": "2026/0001.00",
    "street": 'רמב"ן',
    "house_number": "24",
    "neighborhood": "קטמון הישנה",
    "publication_date": "2026-11-10",
    "objection_deadline": None,
    "in_polygon": None,
}


def _point_fixtures(tmp_path):
    evidence = {
        "tik_num": "2026/0001.00",
        "street": 'רמב"ן',
        "house_number": "24",
        "neighborhood": "קטמון הישנה",
        "crs": "EPSG:2039",
        "x": 220378,
        "y": 631339,
        "verified_at": "2026-11-16",
        "source_url": (
            "https://ykpubdata.jerusalem.muni.il/#/Details"
            "?TikNum=2026/0001.00&SystemCode=26400046&Page=LocationInfo"
        ),
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps([evidence], ensure_ascii=False), encoding="utf-8"
    )
    lon, lat = Transformer.from_crs(2039, 4326, always_xy=True).transform(
        220378, 631339
    )
    ring = [
        [lon - 0.001, lat - 0.001],
        [lon + 0.001, lat - 0.001],
        [lon + 0.001, lat + 0.001],
        [lon - 0.001, lat + 0.001],
        [lon - 0.001, lat - 0.001],
    ]
    council_path = tmp_path / "council.json"
    council_path.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}))
    return evidence_path, council_path


def _run_main(tmp_path, old_rows, new_rows, extra=None):
    old = tmp_path / "old.json"
    old.write_text(json.dumps(old_rows, ensure_ascii=False), encoding="utf-8")
    new = tmp_path / "new.json"
    new.write_text(json.dumps(new_rows, ensure_ascii=False), encoding="utf-8")
    permits = tmp_path / "permits.json"
    permits.write_text("[]", encoding="utf-8")
    parcels = tmp_path / "parcels.json"
    parcels.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    out_active = tmp_path / "active.json"
    out_new = tmp_path / "alert.json"
    argv = [
        "--old",
        str(old),
        "--new",
        str(new),
        "--permits",
        str(permits),
        "--parcels",
        str(parcels),
        "--out-active",
        str(out_active),
        "--out-new",
        str(out_new),
    ] + list(extra or [])
    return argv, out_active, out_new


def test_main_wires_official_point_fallback(tmp_path, capsys):
    evidence_path, council_path = _point_fixtures(tmp_path)
    argv, out_active, out_new = _run_main(
        tmp_path,
        [dict(FALLBACK_ROW)],
        [dict(FALLBACK_ROW)],
        ["--point-evidence", str(evidence_path), "--council", str(council_path)],
    )
    rc = watch.main(argv)
    assert rc == 0
    active = json.loads(out_active.read_text(encoding="utf-8"))
    assert len(active) == 1
    assert active[0]["in_polygon"] is True
    assert active[0]["in_polygon_source"] == "publication_point_evidence"
    payload = json.loads(out_new.read_text(encoding="utf-8"))
    assert [r["tik_num"] for r in payload["new_in_polygon"]] == ["2026/0001.00"]
    assert payload["new_in_polygon"][0]["in_polygon_source"] == (
        "publication_point_evidence"
    )
    assert "[POINT-EVIDENCE]" in capsys.readouterr().out


def test_main_logs_regressed_point_rows(tmp_path, capsys):
    resolved = dict(
        FALLBACK_ROW,
        in_polygon=True,
        in_polygon_source="publication_point_evidence",
    )
    absent = tmp_path / "absent.json"  # evidence removed: no fallback
    argv, out_active, out_new = _run_main(
        tmp_path,
        [resolved],
        [dict(FALLBACK_ROW)],
        ["--point-evidence", str(absent), "--council", str(tmp_path / "none.json")],
    )
    rc = watch.main(argv)
    assert rc == 0
    active = json.loads(out_active.read_text(encoding="utf-8"))
    assert len(active) == 1 and active[0]["in_polygon"] is None
    payload = json.loads(out_new.read_text(encoding="utf-8"))
    assert payload == {"new_in_polygon": [], "unresolved_new": []}
    out = capsys.readouterr().out
    assert "REGRESSED" in out and "2026/0001.00" in out
