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

from ginot import diff, iplan, outputs, page, tracking


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
    ap.add_argument("--site", default="docs")
    ap.add_argument("--base-url", default="https://reihlinstinct.github.io/ginot-hair-plans/")
    ap.add_argument("--snapshots", default="snapshots")
    ap.add_argument("--status", default="data/plan_status.json")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.snapshots, exist_ok=True)

    council = load_council(args.council)
    features = iplan.query_plans(council, service="xplan_without_77_78")
    rows = outputs.rows_from_features(features, council)
    states = tracking.load(args.status)
    rows, changed_defaults = tracking.merge(rows, states)
    if changed_defaults:
        tracking.save(states, args.status)
    # planner tracking data stays local - public artifacts carry only the
    # machine-derived advisory urgency flag
    for row in rows:
        row["advisory_urgent"] = row.pop("tracking_urgent_advisory", False)
        for k in ("tracking_state", "tracking_note", "tracking_updated"):
            row.pop(k, None)
    for row in rows:
        pdir = os.path.join("plans", str(row["pl_number"]).replace("/", "_"))
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, "plan.json"), "w", encoding="utf-8") as fh:
            json.dump(row, fh, ensure_ascii=False, indent=1)
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
        with open(snap_path, encoding="utf-8") as fh:
            old_rows = json.load(fh)["rows"]
    changes = diff.diff_snapshots(old_rows, rows)
    with open(f"{args.out}/changes.json", "w", encoding="utf-8") as fh:
        json.dump({"date": datetime.date.today().isoformat(), "changes": changes},
                  fh, ensure_ascii=False)
    with open(snap_path, "w", encoding="utf-8") as fh:
        json.dump({"date": datetime.date.today().isoformat(), "rows": rows,
                   "plans_77_78": slim}, fh, ensure_ascii=False)
    page.render_site(rows, changes, args.site, base_url=args.base_url)
    badge_dir = os.path.join(args.site, "badge")
    os.makedirs(badge_dir, exist_ok=True)
    for name, msg, color in [("plans", str(len(rows)), "blue"),
                             ("updated", datetime.date.today().isoformat(), "green")]:
        with open(os.path.join(badge_dir, f"{name}.json"), "w") as fh:
            json.dump({"schemaVersion": 1, "label": name, "message": msg, "color": color}, fh)
    # per-status plan-count badges (stable slugs for README links)
    from collections import Counter
    # match order matters: "במילוי תנאים להפקדה" is conditions, not deposit;
    # "הכרעה ... / אישור" is decision, not approved
    # English badge labels: Hebrew renders badly in shields badges (#30)
    slug = {"תנאים": ("status_conditions", "purple", "Fulfilling conditions"),
            "הפקדה": ("status_deposit", "orange", "Deposit for objections"),
            "בדיקה": ("status_review", "blue", "Planning review"),
            "הכרעה": ("status_decision", "yellow", "Decision on objections"),
            "בהליך": ("status_inproc", "brightgreen", "In approval process"),
            "אישור": ("status_approved", "green", "Approved")}
    counts = Counter(r.get("station_desc") or "(ללא)" for r in rows)
    written = set()
    for st, n in sorted(counts.items()):
        fname, color, label = next((v for k, v in slug.items() if k in st),
                                   ("status_other", "lightgrey", "Other"))
        if fname in written:  # multiple statuses mapping to one slug
            fname = f"{fname}_{abs(hash(st)) % 1000}"
        written.add(fname)
        with open(os.path.join(badge_dir, f"{fname}.json"), "w") as fh:
            json.dump({"schemaVersion": 1, "label": label, "message": str(n), "color": color}, fh)
    print(f"{len(rows)} plans, {len(changes)} changes, {len(slim)} in 77/78 track")


if __name__ == "__main__":
    main()
