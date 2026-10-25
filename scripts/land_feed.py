#!/usr/bin/env python3
"""Fetch per-plan deposit-publication status from the Israel Land
Authority public TabaSearch API (apps.land.gov.il) and write
data/land_plan_status.json.

The API is the backend of the RMI public plan-search site: keyless, no
login, no challenge (verified 2026-10-19). One POST per plan, paced,
stop on repeated failures. No personal data involved - plan-level
public metadata only (status, status date, plan id).

Usage: python3 scripts/land_feed.py [--data-json docs/data.json]
"""

import argparse
import datetime
import json
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

URL = "https://apps.land.gov.il/TabaSearch/api/SerachPlans/GetPlans"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DEPOSIT_MARKERS = ("הפקדה", "התנגדויות")
PACE_SECONDS = 1.5
MAX_CONSECUTIVE_FAILURES = 5


def query_plan(plan_number):
    body = json.dumps(
        {
            "planNumber": plan_number,
            "city": "",
            "gush": "",
            "chelka": "",
            "statuses": "",
            "planningCommitte": "",
            "planTypes": "",
            "planTypesUsed": "",
            "fromStatusDate": "",
            "toStatusDate": "",
        }
    )
    cmd = [
        "curl",
        "-s",
        "-m",
        "45",
        "-A",
        UA,
        "-H",
        "Content-Type: application/json",
        "-X",
        "POST",
        "--data",
        body,
        URL,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # #399 production-path policy: a malformed response here already feeds
        # the caller's own failures counter / abort-after-N-consecutive logic
        # (see main()), so it is counted and reported there - no change needed
        # beyond narrowing the caught type to what json.loads actually raises.
        return None
    plans = data.get("plansSmall") if isinstance(data, dict) else None
    if not plans:
        return {}
    exact = [p for p in plans if p.get("planNumber") == plan_number]
    return exact[0] if exact else plans[0]


def parse_status_date(raw):
    """' 21/08/26' -> '2026-08-21' (dd/mm/yy); '' when unparseable."""
    raw = (raw or "").strip()
    try:
        d, m, y = raw.split("/")
        y = int(y)
        y = 2000 + y if y < 100 else y
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        # #399: tested reject-gracefully helper (test_land_status_date_parsing
        # asserts "" for "", None, an invalid day, and garbage) - an absent or
        # malformed status date is the normal case here, not a dropped
        # record, so narrowed to the one exception str.split/int/date can
        # raise and left returning "" (no behavior change).
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-json", default="docs/data.json")
    ap.add_argument("--tracked", default="data/mavat_tracked_plans.json")
    ap.add_argument("--out", default="data/land_plan_status.json")
    args = ap.parse_args()

    numbers = set()
    try:
        with open(args.data_json, encoding="utf-8") as fh:
            for row in json.load(fh).get("rows", []):
                if row.get("pl_number"):
                    numbers.add(row["pl_number"])
    except FileNotFoundError:
        pass
    try:
        with open(args.tracked, encoding="utf-8") as fh:
            for p in json.load(fh).get("plans", []):
                numbers.add(p["plan_number"])
    except FileNotFoundError:
        pass
    numbers = sorted(numbers)
    print(f"{len(numbers)} plan numbers to query")

    result, failures = {}, 0
    for i, num in enumerate(numbers):
        if i:
            time.sleep(PACE_SECONDS)
        try:
            hit = query_plan(num)
        except (subprocess.SubprocessError, OSError):
            # #399: query_plan's own body only risks a subprocess/OS failure
            # here (its internal JSON parsing already narrows and returns
            # None); a None `hit` is already counted via `failures` below and
            # the run aborts after MAX_CONSECUTIVE_FAILURES - compliant,
            # narrowed only.
            hit = None
        if hit is None:
            failures += 1
            print(
                f"[{i + 1}/{len(numbers)}] {num}: request failed ({failures} consecutive)"
            )
            if failures >= MAX_CONSECUTIVE_FAILURES:
                print("aborting: repeated request failures")
                return 1
            continue
        failures = 0
        if not hit:
            continue
        status = hit.get("status") or ""
        result[num] = {
            "land_status": status,
            "land_status_date": parse_status_date(hit.get("statusDate")),
            "land_plan_id": hit.get("planId"),
            "land_city": hit.get("cityText"),
            "is_deposit_publication": any(m in status for m in DEPOSIT_MARKERS),
        }
        if (i + 1) % 25 == 0:
            print(f"[{i + 1}/{len(numbers)}] ok, {len(result)} with land data")

    payload = {
        "generated": datetime.datetime.now(ZoneInfo("Asia/Jerusalem"))
        .date()
        .isoformat(),  # issue #331: IL not runner UTC
        "source": "Israel Land Authority TabaSearch public API",
        "plans": result,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {len(result)} plans with land status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
