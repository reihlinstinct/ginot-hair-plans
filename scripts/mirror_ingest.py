#!/usr/bin/env python3
"""Bulk permit-request ingest from the over.org.il mirror (issue #74).

Pulls the Jerusalem licensing case files (ykpubdata) from the over.org.il
(גרסאות לעם) public mirror - a third-party scraper with a free, keyless
API - instead of scanning the municipality API parcel by parcel. The
mirror carries per-tik status, request type, address and gush/parcel
range with first_seen/last_seen sample tracking, which doubles as
change detection: a nightly diff of this file shows new/changed tiks
with zero load on the municipality.

The mirror does NOT carry s.149 publication dates (process steps) -
those still come from the direct scanner (scripts/vpn/permit_feed.py),
fetched only for tiks the mirror shows as new or changed.

Privacy: the mirror's בעלי עניין column (personal names) is dropped on
ingest and never written out. Output is DRAFT-labelled third-party
data; verify at the source before reliance.

Usage: python3 scripts/mirror_ingest.py [--validate-against data/permit_requests.json]
"""
import argparse
import datetime
import json
import subprocess
import time
import urllib.parse

DATASET = "76f0e069-f269-46fc-bcc8-f704ebbf17ff"
ROWS_URL = f"https://www.over.org.il/api/append/{DATASET}/datastore_search"
TABLE = "append_ykpubdata_all_665e9000_76f0e069"
PAGE = 500
PACE_SECONDS = 1.0
# columns we never read out of the mirror (personal data)
PERSONAL_COLUMNS = {"בעלי עניין"}


def load_parcels(path):
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    by_gush = {}
    for f in gj.get("features", []):
        p = f.get("properties", {})
        g, h = p.get("gush"), p.get("helka")
        if g and h:
            by_gush.setdefault(int(g), set()).add(int(h))
    return by_gush


def parcel_interval(row):
    """Parcel range מחלקה..עד חלקה as (points, interval).

    Ranges can legitimately span thousands of sub-parcels (a
    common-property registration covers a parent parcel and all its
    בית משותף sub-parcels, seen as 22 -> 5032), so membership is tested
    as an interval, never materialized. Garbage ranges (start > end,
    seen as 216 -> 2) degrade to the two endpoints as points.
    """
    def num(v):
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            return None
    start, end = num(row.get("מחלקה")), num(row.get("עד חלקה"))
    if start is None:
        return set(), None
    if end is None:
        end = start
    if start > end:
        return {start, end}, None
    return set(), (start, end)


def matching_parcels(row, parcels_by_gush):
    try:
        gush = int(float(str(row.get("גוש", "")).strip()))
    except (TypeError, ValueError):
        return 0, []
    council = parcels_by_gush.get(gush, set())
    points, interval = parcel_interval(row)
    if interval:
        hits = sorted(p for p in council if interval[0] <= p <= interval[1])
    else:
        hits = sorted(points & council)
    return gush, hits


def date_only(raw):
    return (raw or "").strip()[:10]


def map_record(row, gush, hits):
    """Mirror row -> output record. Personal columns are never read."""
    street = " ".join(x for x in ((row.get("רחוב") or "").strip(),
                                  (row.get("מספר בית") or "").strip()) if x and x != "0")
    neighborhood = (row.get("שכונה") or "").strip()
    return {
        "tik_num": (row.get("מספר תיק") or "").strip(),
        "status": (row.get("סטטוס") or "").strip(),
        "status_date": date_only(row.get("תאריך סטטוס")),
        "sugbakasha": (row.get("סוג בקשה") or "").strip(),
        "mahut": (row.get("מהות הבקשה") or "").strip(),
        "address": " ".join(x for x in (street, neighborhood) if x),
        "gush": gush,
        "parcels": hits,
        "mirror_sample_date": date_only(row.get("תאריך דגימה")),
        "mirror_first_seen": row.get("first_seen") or "",
        "mirror_last_seen": row.get("last_seen") or "",
    }


def fetch_rows(gushim):
    """Paged latest-view pull filtered to the council gushim."""
    filters = urllib.parse.quote(json.dumps({"גוש": [str(g) for g in gushim]},
                                            ensure_ascii=False))
    rows, offset = [], 0
    while True:
        url = (f"{ROWS_URL}?latest=true&limit={PAGE}&offset={offset}"
               f"&include_total=true&filters={filters}")
        out = subprocess.run(["curl", "-s", "-m", "60", url],
                             capture_output=True, text=True).stdout
        data = json.loads(out)
        if not data.get("success"):
            raise RuntimeError(f"mirror API error: {out[:200]}")
        result = data["result"]
        batch = result.get("records", [])
        rows.extend(batch)
        print(f"fetched {len(rows)}/{result.get('total')} mirror rows")
        if len(rows) >= result.get("total", 0) or not batch:
            return rows
        offset += PAGE
        time.sleep(PACE_SECONDS)


def validate(records, path):
    """Compare mirror records against the direct-scanner output."""
    with open(path, encoding="utf-8") as fh:
        direct = json.load(fh).get("requests", [])
    direct_tiks = {r["tik_num"] for r in direct}
    mirror_tiks = set(records)
    common = direct_tiks & mirror_tiks
    print(f"validation vs {path}:")
    print(f"  direct-scan tiks: {len(direct_tiks)}")
    print(f"  mirror tiks (council parcels): {len(mirror_tiks)}")
    print(f"  in both: {len(common)}")
    print(f"  direct-only: {sorted(direct_tiks - mirror_tiks)[:20]}")
    return {"direct": len(direct_tiks), "mirror": len(mirror_tiks),
            "common": len(common),
            "direct_only": sorted(direct_tiks - mirror_tiks)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", default="data/ginot_hair_parcels.geojson")
    ap.add_argument("--out", default="data/permit_mirror.json")
    ap.add_argument("--validate-against", default="")
    args = ap.parse_args()

    parcels_by_gush = load_parcels(args.parcels)
    gushim = sorted(parcels_by_gush)
    print(f"{sum(len(v) for v in parcels_by_gush.values())} council parcels "
          f"in {len(gushim)} gushim")

    records = {}
    for row in fetch_rows(gushim):
        if PERSONAL_COLUMNS & row.keys():
            row = {k: v for k, v in row.items() if k not in PERSONAL_COLUMNS}
        gush, hits = matching_parcels(row, parcels_by_gush)
        if not hits:
            continue  # tik touches no council parcel
        rec = map_record(row, gush, hits)
        if rec["tik_num"]:
            records[rec["tik_num"]] = rec

    payload = {
        "generated": datetime.date.today().isoformat(),
        "source": ("over.org.il (גרסאות לעם) mirror of the Jerusalem "
                   "municipality ykpubdata licensing viewer"),
        "mirror_table": TABLE,
        "label": ("DRAFT - third-party mirror data; completeness not "
                  "guaranteed, verify at the source before reliance"),
        "requests": sorted(records.values(), key=lambda r: r["tik_num"]),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {len(records)} requests on council parcels")

    if args.validate_against:
        validate(records, args.validate_against)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
