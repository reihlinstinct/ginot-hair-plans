#!/usr/bin/env python3
"""Regenerate docs/permits.html from data/permit_requests.json (#405).

The permit feed updates data/permit_requests.json on every batch, but the
permits fragment the site loads was only rebuilt by the weekly refresh -
a newly published permit stayed invisible on the site for up to a week
(user report 2026-10-24: publication-status tik 2026/0439.00 missing).
This script re-renders ONLY the fragment through the same _permits_section
code path as the weekly site build: no plan rows, no network. It runs in
the permit-feed publish step under set -e, so a render failure fails the
run red instead of silently shipping stale rows.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ginot.mapdata import write_permit_points
from ginot.page import _permits_section, publication_evidence_tiks, write_permit_ids

DATA = "data/permit_requests.json"
OUT = "docs/permits.html"
# #441: the small default-view subset the page loads first; the full list
# above loads only on a non-default interaction. Same source, same batch.
DEFAULT_OUT = "docs/permits-default.html"
PUBLICATIONS = "data/publications_active.json"
IDS_OUT = "docs/permit-ids.json"  # read by the submit worker (#515)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-dependencies', action='store_true',
                        help='Check imports without reading or changing data')
    args = parser.parse_args()
    if args.check_dependencies:
        print('permit renderer dependencies available')
        return 0
    with open(DATA, encoding="utf-8") as fh:
        permits = json.load(fh).get("requests", [])
    if not permits:
        print(f"{DATA} has no requests - refusing to empty the fragment")
        return 1
    permit_map = write_permit_points(permits, 'data/ginot_hair_parcels.geojson', 'docs/permit-points.json')
    missing = set(permit_map['missing_location'])
    permits = [dict(p, _map_missing=p.get('tik_num') in missing) for p in permits]
    if not _permits_section(permits, rows_file=OUT, default_rows_file=DEFAULT_OUT,
                            evidence_tiks=publication_evidence_tiks(PUBLICATIONS)):
        print("permits section render produced no output")
        return 1
    print(f"rendered {len(permits)} permit rows into {OUT} and the default subset into {DEFAULT_OUT}")
    n = write_permit_ids(permits, IDS_OUT)
    print(f"wrote {n} permit ids into {IDS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
