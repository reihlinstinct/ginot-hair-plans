#!/usr/bin/env python3
"""Tiered re-check parcel selector (issue #342). Pure, no network.

Tier "active": parcels with at least one request that can still change
(status not terminal and not late-stage). Re-checked often.
Tier "rotation": every other already-scanned parcel, oldest check first
(parcels never checked go first), capped per run. Slow rotation.

Public data only: gush/helka numbers and status text already in the feed.
Usage: python3 scripts/vpn/recheck_select.py --tier active|rotation [--cap 150]
Prints a JSON list of [gush, helka] pairs.
"""
import argparse
import json

# Kept in step with permit_enrich.TERMINAL_STATUSES / LATE_STAGE_STATUSES
# (not imported: this module must stay free of network/VPN code).
TERMINAL_STATUSES = {"הבקשה נסגרה", "הופק-הוצא היתר בניה",
                     "הופק היתר מוארך", "נדחתה"}
LATE_STAGE_STATUSES = {
    "הוכנה טיוטת היתר בניה",
    "התקבל תיק ורוד / מסמכים חתומים",
    "שולמה מקדמה",
    "אושר ע\"י מהנדס העיר",
    "הבקשה נגנזה",
}


def is_active(status):
    return status not in TERMINAL_STATUSES and status not in LATE_STAGE_STATUSES


def parcel_key(r):
    return (int(r["gush"]), int(r["helka"]))


def active_parcels(requests, stale_before=None, cap=None):
    """Parcels with a changeable request, oldest check first. With
    stale_before (YYYY-MM-DD) only parcels with an active request not
    checked on or after that day; cap bounds the run time."""
    last = {}
    for r in requests:
        if not (r.get("gush") and r.get("helka") and is_active(r.get("status", ""))):
            continue
        d = r.get("details_checked_on") or ""
        k = parcel_key(r)
        last[k] = d if k not in last else min(last[k], d)
    keys = [k for k, d in last.items() if stale_before is None or d < stale_before]
    keys.sort(key=lambda k: (last[k], k))
    return keys if cap is None else keys[:max(0, cap)]


def rotation_parcels(requests, all_parcels, scanned_upto, cap):
    """Non-active scanned parcels, never-checked first, then oldest check.
    all_parcels is the sorted parcel list; scanned_upto the scan cursor, so
    parcels the main scan has not reached yet are left to it."""
    active = set(active_parcels(requests))
    last = {}
    for r in requests:
        if not (r.get("gush") and r.get("helka")):
            continue
        k = parcel_key(r)
        d = r.get("details_checked_on") or ""
        if d > last.get(k, ""):
            last[k] = d
    scanned = all_parcels[:max(0, scanned_upto)]
    rest = [p for p in scanned if p not in active]
    rest.sort(key=lambda p: (last.get(p, ""), p))
    return rest[:max(0, cap)]


def all_parcels_of(geojson):
    out = set()
    for f in geojson.get("features", []):
        p = f.get("properties", {})
        if p.get("gush") and p.get("helka"):
            out.add((int(p["gush"]), int(p["helka"])))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=("active", "rotation"), required=True)
    ap.add_argument("--feed", default="data/permit_requests.json")
    ap.add_argument("--parcels", default="data/ginot_hair_parcels.geojson")
    ap.add_argument("--cap", type=int, default=150)
    ap.add_argument("--stale-before", default=None,
                    help="active tier: only parcels with an active request not checked since DATE")
    args = ap.parse_args()
    with open(args.feed, encoding="utf-8") as fh:
        feed = json.load(fh)
    requests = feed.get("requests", [])
    if args.tier == "active":
        sel = active_parcels(requests, args.stale_before,
                             args.cap if args.stale_before else None)
    else:
        with open(args.parcels, encoding="utf-8") as fh:
            parcels = all_parcels_of(json.load(fh))
        b = feed.get("batch", {})
        sel = rotation_parcels(requests, parcels,
                               b.get("offset", 0) + b.get("limit", 0), args.cap)
    print(json.dumps([list(p) for p in sel]))


if __name__ == "__main__":
    main()
