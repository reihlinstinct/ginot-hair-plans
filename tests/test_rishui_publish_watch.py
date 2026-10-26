"""Unit tests for the daily active-publications diff (issue #527)."""
import importlib.util
import json
from pathlib import Path

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
OUT_ROW = {"myIndex": 3, "tik_num": "2026/9999.00", "neighborhood": "רמות", "in_polygon": False}
UNRESOLVED_ROW = {"myIndex": 4, "tik_num": "2026/0001.00", "neighborhood": None, "in_polygon": None}
OLD = [{"myIndex": 1, "neighborhood": "קטמון הישנה", "in_polygon": True}]


def test_seed_writes_baseline_without_alerts():
    baseline, payload, seeded = watch.update(None, [IN_ROW, OUT_ROW])
    assert seeded
    assert baseline == [IN_ROW]  # out-of-polygon row dropped even at seed
    assert payload == {"new_in_polygon": [], "unresolved_new": []}


def test_new_in_polygon_row_is_reported_and_outside_ignored():
    baseline, payload, seeded = watch.update(OLD, OLD + [IN_ROW, OUT_ROW, UNRESOLVED_ROW])
    assert not seeded
    assert payload["new_in_polygon"] == [IN_ROW]
    assert payload["unresolved_new"] == [UNRESOLVED_ROW]
    # baseline keeps in-polygon + unresolved, drops out-of-polygon
    assert baseline == OLD + [IN_ROW, UNRESOLVED_ROW]


def test_unresolved_row_not_reflagged_daily():
    baseline, payload, _ = watch.update(OLD, OLD + [UNRESOLVED_ROW])
    _, payload2, _ = watch.update(baseline, baseline)
    assert payload2 == {"new_in_polygon": [], "unresolved_new": []}


def test_main_roundtrip(tmp_path):
    new = tmp_path / "new.json"
    new.write_text(json.dumps([IN_ROW, OUT_ROW], ensure_ascii=False), encoding="utf-8")
    permits = tmp_path / "permits.json"
    permits.write_text(json.dumps([
        {"tik_num": "2026/0439.00", "gush": 30016, "helka": 87},
        {"tik_num": "2026/9999.00", "gush": 99999, "helka": 1},
    ]), encoding="utf-8")
    parcels = tmp_path / "parcels.json"
    parcels.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"gush": 30016, "helka": 87}, "geometry": None}
    ]}), encoding="utf-8")
    out_active = tmp_path / "active.json"
    out_new = tmp_path / "alert.json"
    rc = watch.main(
        ["--old", str(tmp_path / "missing.json"), "--new", str(new),
         "--permits", str(permits), "--parcels", str(parcels),
         "--out-active", str(out_active), "--out-new", str(out_new)]
    )
    assert rc == 0
    # main re-resolves from permits+parcels: IN_ROW in-polygon; OUT_ROW's parcel
    # is outside the polygon parcel set -> dropped
    active = json.loads(out_active.read_text(encoding="utf-8"))
    assert [r["tik_num"] for r in active] == ["2026/0439.00"]
    assert active[0]["in_polygon"] is True
    assert json.loads(out_new.read_text(encoding="utf-8")) == {"new_in_polygon": [], "unresolved_new": []}


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
    assert "git diff --cached --quiet" in workflow
    assert "scripts/vpn/l2tp.py down" in workflow
