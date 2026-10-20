#!/usr/bin/env python3
"""Publication-date enrichment for mirror-ingested tiks (issue #76).

Runs through the owner-operated L2TP tunnel. For each selected tik it
fetches ONLY the process-step procedure (242700451, publication dates -
process metadata, no personal data) and writes the s.149 dates back
into data/permit_mirror.json. The details procedure (personal data) is
never called; addresses already come from the mirror.

Selection: tiks in data/permit_mirror_diff.json's changed list (the
nightly path), plus - with --include-unenriched - active-status tiks
never enriched (the one-time backfill, batched with --offset/--limit).
Stops red on any anti-bot challenge (no workaround).

Usage: python3 scripts/vpn/permit_enrich.py [--include-unenriched] [--offset 0] [--limit 2000]
"""
import argparse
import json
import sys
import time

from permit_feed import SYS, call, publication_dates, PACE_SECONDS

MIRROR = "data/permit_mirror.json"
DIFF = "data/permit_mirror_diff.json"
SPOTCHECK = "data/permit_enrich_spotcheck.json"
SPOTCHECK_MAX = 10
# statuses where no s.149 publication can still start (request is over)
TERMINAL_STATUSES = {"הבקשה נסגרה", "הופק-הוצא היתר בניה",
                     "הופק היתר מוארך", "נדחתה"}


# Late-stage statuses: the s.149 publication already happened (or never
# applies), so the one-time backfill skips them by default (owner decision
# 2026-10-20, issue #99). Widen with --include-late-stages. Tiks the
# nightly mirror diff reports as new/changed are still fetched.
LATE_STAGE_STATUSES = {
    "הוכנה טיוטת היתר בניה",
    "התקבל תיק ורוד / מסמכים חתומים",
    "שולמה מקדמה",
    "אושר ע\"י מהנדס העיר",
    "הבקשה נגנזה",
}


def step_summary(tik):
    """Process-step names and which date fields exist, for tiks that came
    back without publication dates (spot check, issue #102). Step names and
    date presence only: process metadata, no personal data, no dates."""
    rows = call(242700451, {"SystemID": SYS, "TikNum": tik}) or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        out.append({"step": r.get("stepCodeText") or "",
                    "has_exec_date": bool(r.get("execDateStr")),
                    "has_plan_date": bool(r.get("planDateStr"))})
    return out


def select_tiks(requests, diff_tiks, include_unenriched, include_late_stages=False):
    """Tiks to (re)fetch publication dates for, in stable order."""
    selected = []
    for r in requests:
        if r["status"] in TERMINAL_STATUSES:
            continue
        if r["tik_num"] in diff_tiks:
            selected.append(r["tik_num"])
        elif (include_unenriched and "publication_start" not in r
              and (include_late_stages or r["status"] not in LATE_STAGE_STATUSES)):
            selected.append(r["tik_num"])
    return sorted(set(selected))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", default=MIRROR)
    ap.add_argument("--diff", default=DIFF)
    ap.add_argument("--include-unenriched", action="store_true")
    ap.add_argument("--include-late-stages", action="store_true",
                    help="backfill also late-stage statuses (default: skipped)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--count-only", action="store_true",
                    help="print the number of selected tiks and exit "
                         "(no fetching; used by the self-chaining guard, "
                         "issue #145)")
    args = ap.parse_args()

    with open(args.mirror, encoding="utf-8") as fh:
        payload = json.load(fh)
    requests = payload["requests"]
    try:
        with open(args.diff, encoding="utf-8") as fh:
            diff = json.load(fh)
        diff_tiks = set(diff.get("new_tiks", []) + diff.get("changed_tiks", []))
    except (FileNotFoundError, json.JSONDecodeError):
        diff_tiks = set()

    todo = select_tiks(requests, diff_tiks, args.include_unenriched,
                       args.include_late_stages)
    if args.count_only:
        print(len(todo))
        return 0
    batch = todo[args.offset:args.offset + args.limit]
    print(f"{len(todo)} tiks selected; enriching batch of {len(batch)} "
          f"(offset={args.offset})")
    if not batch:
        print("nothing to enrich")
        return 0

    by_tik = {r["tik_num"]: r for r in requests}
    done = 0
    spot = []
    for i, tik in enumerate(batch):
        if i:
            time.sleep(PACE_SECONDS)
        try:
            start, end = publication_dates(tik)
        except RuntimeError:
            print("anti-bot challenge - stopping (no workaround)")
            return 2
        except Exception as exc:
            print(f"{tik}: publication fetch failed: {exc}")
            continue
        if not start and not end and len(spot) < SPOTCHECK_MAX:
            try:
                spot.append({"tik_num": tik, "status": by_tik[tik]["status"],
                             "steps": step_summary(tik)})
            except Exception as exc:
                print(f"{tik}: spot check failed: {exc}")
        by_tik[tik]["publication_start"] = start
        by_tik[tik]["publication_end_planned"] = end
        done += 1
        if (i + 1) % 50 == 0:
            print(f"[{i+1}/{len(batch)}] enriched {done}")

    with open(args.mirror, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    if spot:
        with open(SPOTCHECK, "w", encoding="utf-8") as fh:
            json.dump({"note": "tiks fetched with no publication dates: step names and date presence only",
                       "samples": spot}, fh, ensure_ascii=False, indent=1)
    remaining = len(todo) - (args.offset + len(batch))
    print(f"enriched {done}/{len(batch)} tiks; {max(remaining, 0)} remain "
          f"after this batch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
