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

from permit_feed import PACE_SECONDS, SYS, call, publication_dates

MIRROR = "data/permit_mirror.json"
DIFF = "data/permit_mirror_diff.json"
SPOTCHECK = "data/permit_enrich_spotcheck.json"
PENDING = "data/permit_enrich_pending.json"
SPOTCHECK_MAX = 10
# statuses where no s.149 publication can still start (request is over)
TERMINAL_STATUSES = {"הבקשה נסגרה", "הופק-הוצא היתר בניה", "הופק היתר מוארך", "נדחתה"}


# Late-stage statuses: the s.149 publication already happened (or never
# applies), so the one-time backfill skips them by default (owner decision
# 2026-10-20, issue #99). Widen with --include-late-stages. Tiks the
# nightly mirror diff reports as new/changed are still fetched.
LATE_STAGE_STATUSES = {
    "הוכנה טיוטת היתר בניה",
    "התקבל תיק ורוד / מסמכים חתומים",
    "שולמה מקדמה",
    'אושר ע"י מהנדס העיר',
    "הבקשה נגנזה",
}


def step_summary(tik):
    """Process-step names and which date fields exist, for tiks that came
    back without publication dates (spot check, issue #102). Step names and
    date presence only: process metadata, no personal data, no dates."""
    rows = call(242700451, {"SystemID": SYS, "TikNum": tik}) or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        out.append(
            {
                "step": r.get("stepCodeText") or "",
                "has_exec_date": bool(r.get("execDateStr")),
                "has_plan_date": bool(r.get("planDateStr")),
            }
        )
    return out


def load_pending(path=PENDING):
    """Tiks whose last publication fetch failed (retry queue, issue #492)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(t) for t in data.get("pending", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_pending(pending, path=PENDING):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"pending": sorted(pending)}, fh, ensure_ascii=False, indent=1)


def prune_pending(pending, by_tik):
    """Drop retry-queue entries for tiks gone from the mirror or terminal."""
    return {
        t
        for t in pending
        if t in by_tik and by_tik[t]["status"] not in TERMINAL_STATUSES
    }


def select_tiks(requests, diff_tiks, include_unenriched, include_late_stages=False):
    """Tiks to (re)fetch publication dates for, in stable order."""
    selected = []
    for r in requests:
        if r["status"] in TERMINAL_STATUSES:
            continue
        if r["tik_num"] in diff_tiks or (
            include_unenriched
            and "publication_start" not in r
            and (include_late_stages or r["status"] not in LATE_STAGE_STATUSES)
        ):
            selected.append(r["tik_num"])
    return sorted(set(selected))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", default=MIRROR)
    ap.add_argument("--diff", default=DIFF)
    ap.add_argument("--pending", default=PENDING)
    ap.add_argument("--include-unenriched", action="store_true")
    ap.add_argument(
        "--include-late-stages",
        action="store_true",
        help="backfill also late-stage statuses (default: skipped)",
    )
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument(
        "--count-only",
        action="store_true",
        help="print the number of selected tiks and exit "
        "(no fetching; used by the self-chaining guard, "
        "issue #145)",
    )
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
    pending = load_pending(args.pending)
    # Failed fetches ride the next run's selection even after the nightly
    # ingest rewrites the diff (issue #492).
    diff_tiks |= pending

    todo = select_tiks(
        requests, diff_tiks, args.include_unenriched, args.include_late_stages
    )
    if args.count_only:
        print(len(todo))
        return 0
    batch = todo[args.offset : args.offset + args.limit]
    print(
        f"{len(todo)} tiks selected; enriching batch of {len(batch)} "
        f"(offset={args.offset})"
    )
    by_tik = {r["tik_num"]: r for r in requests}
    if not batch:
        # Terminal/gone pending tiks are never selected, so an empty batch
        # is exactly where dead entries would otherwise linger (#492).
        save_pending(prune_pending(pending, by_tik), args.pending)
        print("nothing to enrich")
        return 0

    done = 0
    spot = []
    failed = set()
    succeeded = set()
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
            failed.add(tik)
            continue
        succeeded.add(tik)
        if not start and not end and len(spot) < SPOTCHECK_MAX:
            try:
                spot.append(
                    {
                        "tik_num": tik,
                        "status": by_tik[tik]["status"],
                        "steps": step_summary(tik),
                    }
                )
            except Exception as exc:
                print(f"{tik}: spot check failed: {exc}")
        by_tik[tik]["publication_start"] = start
        by_tik[tik]["publication_end_planned"] = end
        done += 1
        if (i + 1) % 50 == 0:
            print(f"[{i + 1}/{len(batch)}] enriched {done}")

    with open(args.mirror, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    new_pending = prune_pending((pending - succeeded) | failed, by_tik)
    save_pending(new_pending, args.pending)
    if new_pending:
        print(f"{len(new_pending)} tiks queued for retry on the next enrich run")
    if spot:
        with open(SPOTCHECK, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "note": "tiks fetched with no publication dates: step names and date presence only",
                    "samples": spot,
                },
                fh,
                ensure_ascii=False,
                indent=1,
            )
    remaining = len(todo) - (args.offset + len(batch))
    print(
        f"enriched {done}/{len(batch)} tiks; {max(remaining, 0)} remain "
        f"after this batch"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
