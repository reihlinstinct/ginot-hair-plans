#!/usr/bin/env python3
"""Weekly refresh: query iplan for plans in the Ginot HaIr council polygon,
build CSV/XLSX, diff against the previous snapshot, render the static site.

Usage:
  python refresh.py [--council data/council_ginot_hair.geojson] [--out out/] [--site site/]

The refresh is designed to run from any free scheduler (see README): it is a
plain script with no GitHub Actions dependency.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from shapely.geometry import shape
from ginot import iplan, outputs, diff, page


def load_council(path):
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    # committed GeoJSON is WGS84; project back to EPSG:2039 for the query
    from pyproj import Transformer
    from shapely.ops import transform
    t = Transformer.from_crs("EPSG:4326", "EPSG:2039", always_xy=True)
    return transform(t.transform, shape(gj["geometry"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--council", default="data/council_ginot_hair.geojson")
    ap.add_argument("--out", default="out")
    ap.add_argument("--site", default="site")
    ap.add_argument("--snapshots", default="snapshots")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.snapshots, exist_ok=True)

    council = load_council(args.council)
    features = iplan.query_plans(council, service="xplan_without_77_78")
    rows = outputs.rows_from_features(features, council)
    outputs.write_csv(rows, f"{args.out}/ginot_hair_plans.csv")
    outputs.write_xlsx(rows, f"{args.out}/ginot_hair_plans.xlsx")

    feats77 = iplan.query_plans(council, service="Xplan_77_78", return_geometry=False)
    slim = [{ "pl_number": f["attributes"].get("pl_number"),
              "pl_name": f["attributes"].get("pl_name"),
              "station_desc": f["attributes"].get("station_desc"),
              "mavat_url": f["attributes"].get("pl_url")} for f in feats77]

    snap_path = f"{args.snapshots}/latest.json"
    old_rows = []
    if os.path.exists(snap_path):
        old_rows = json.load(open(snap_path, encoding="utf-8"))["rows"]
    changes = diff.diff_snapshots(old_rows, rows)
    json.dump({"date": datetime.date.today().isoformat(), "changes": changes},
              open(f"{args.out}/changes.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"date": datetime.date.today().isoformat(), "rows": rows,
               "plans_77_78": slim}, open(snap_path, "w", encoding="utf-8"), ensure_ascii=False)
    page.render_site(rows, changes, args.site)
    print(f"{len(rows)} plans, {len(changes)} changes, {len(slim)} in 77/78 track")


if __name__ == "__main__":
    main()
