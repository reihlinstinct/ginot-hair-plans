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
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ginot.page import _permits_section

DATA = "data/permit_requests.json"
OUT = "docs/permits.html"


def main() -> int:
    with open(DATA, encoding="utf-8") as fh:
        permits = json.load(fh).get("requests", [])
    if not permits:
        print(f"{DATA} has no requests - refusing to empty the fragment")
        return 1
    if not _permits_section(permits, rows_file=OUT):
        print("permits section render produced no output")
        return 1
    print(f"rendered {len(permits)} permit rows into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
