import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("build_site_index", ROOT / "scripts" / "build_site_index.py")
bsi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsi)


def test_scan_counts_known_shapes(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"requests": [1, 2, 3]}), encoding="utf-8")
    (tmp_path / "b.geojson").write_text(json.dumps({"features": [{}]}), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps({"other": 1}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("x", encoding="utf-8")
    ds = {d["name"]: d for d in bsi.scan(str(tmp_path))}
    assert ds["a.json"]["records"] == 3
    assert ds["b.geojson"]["records"] == 1 and ds["b.geojson"]["kind"] == "geojson"
    assert ds["c.json"]["records"] is None
    assert ds["broken.json"]["kind"] == "unparsed"
    assert "skip.txt" not in ds


def test_mirror_hold_and_planner_excluded(tmp_path):
    for fn in ("permit_mirror.json", "permit_mirror_diff.json", "plan_status.json",
               "mavat_plan_status.json"):
        (tmp_path / fn).write_text("{}", encoding="utf-8")
    (tmp_path / "land_plan_status.json").write_text("{}", encoding="utf-8")
    names = [d["name"] for d in bsi.scan(str(tmp_path))]
    # owner decision 2026-10-21: mirror data is not linked from the site
    # until the full parcel download completes; planner state is private
    assert names == ["land_plan_status.json"]


def test_committed_index_matches_repo_folder_state(tmp_path):
    # CI staleness gate: a data change without an index rebuild fails here
    out = tmp_path / "index.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site_index.py"),
                    "data", str(out)], check=True, cwd=ROOT)
    fresh = json.loads(out.read_text(encoding="utf-8"))["datasets"]
    committed = json.loads((ROOT / "docs" / "index.json").read_text(encoding="utf-8"))["datasets"]
    assert fresh == committed
