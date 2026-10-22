#!/usr/bin/env python3
"""Build docs/index.json from the state of the repo folders (issue #152).

The public page loads this index and renders its datasets section from it,
so any data file added to the repo appears on the site with its next data
commit - no manual lists, no dedicated Action (the scan rides the same
commit as the data change). CI compares a fresh scan against the committed
index, so a forgotten regeneration fails red.
"""
import datetime
import json
import os
import sys

DATA_DIR = "data"
OUT = "docs/index.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "reihlinstinct/ginot-hair-plans")
BLOB_BASE = f"https://github.com/{REPO}/blob/main/"

# Planner bookkeeping (gitignored; defensive only).
EXCLUDE = {"plan_status.json", "mavat_plan_status.json"}
# Owner decision 2026-10-21: mirror data is linked from the site only after
# the full parcel download completes.
MIRROR_HOLD = {"permit_mirror.json", "permit_mirror_diff.json"}

COUNT_KEYS = ("requests", "rows", "features", "changes", "samples")


def record_count(obj):
    if isinstance(obj, dict):
        for k in COUNT_KEYS:
            if isinstance(obj.get(k), list):
                return len(obj[k])
    if isinstance(obj, list):
        return len(obj)
    return None


def scan(data_dir=DATA_DIR):
    datasets = []
    for fn in sorted(os.listdir(data_dir)):
        path = os.path.join(data_dir, fn)
        if not os.path.isfile(path) or fn in EXCLUDE or fn in MIRROR_HOLD:
            continue
        if fn.endswith(".geojson"):
            kind = "geojson"
        elif fn.endswith(".json"):
            kind = "json"
        else:
            continue
        records = None
        try:
            with open(path, encoding="utf-8") as fh:
                records = record_count(json.load(fh))
        except (json.JSONDecodeError, UnicodeDecodeError):
            kind = "unparsed"
        datasets.append({"name": fn, "path": path, "kind": kind,
                         "records": records, "bytes": os.path.getsize(path),
                         "url": BLOB_BASE + path})
    return datasets


def build(data_dir=DATA_DIR, out=OUT):
    payload = {"generated": datetime.date.today().isoformat(),
               "note": "auto-generated from repo folder state (issue #152) - do not edit by hand",
               "datasets": scan(data_dir)}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return payload


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    p = build(data_dir, out)
    if data_dir == DATA_DIR and out == OUT:
        from parcel_badges import build_badges
        build_badges()
    print(f"wrote {out}: {len(p['datasets'])} datasets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
