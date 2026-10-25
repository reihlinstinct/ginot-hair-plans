#!/usr/bin/env python3
"""Targeted one-off backfill of raw permit address fields (issue #452).

#449 made the renderer label "שכונה: X" when no street address exists, keyed
on the raw fields (rehovName/mispBait/schunaName) that permit_feed.address_of
preserves (#408). Rows scanned before that change carry only the legacy
joined "address" string, and the incremental weekly refresh never re-enriches
them, so the renderer fix is inert for 2,330 measured rows (26 empty address
+ 2,304 with no house number, feed of 2026-10-25).

This script re-enriches exactly that target set through the owner-operated
L2TP tunnel with the feed's own client, pacing (3s), and challenge policy
(stop on any anti-bot marker, exit 2, no workaround). It is a one-off,
resumable batch - NOT wired into the weekly refresh. Progress is flushed
atomically to the data file every --flush-every tiks and mirrored to a
checkpoint file, so --resume after a lost run skips finished tiks.

No invented data: when the source procedure returns no row, the raw fields
are stored empty and the renderer shows its own no-address wording (#449).

Usage:
  python3 scripts/vpn/permit_address_backfill.py --dry-run   # counts only
  python3 scripts/vpn/permit_address_backfill.py [--limit N] [--resume]

Exit codes: 0 = done (or dry run), 2 = anti-bot challenge (stop), 1 = other.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import time

_HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("permit_feed", _HERE / "permit_feed.py")
_feed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_feed)

street_address = _feed.street_address
PACE_SECONDS = _feed.PACE_SECONDS
MAX_CONSECUTIVE_FAILURES = _feed.MAX_CONSECUTIVE_FAILURES

RAW_FIELDS = ("rehovName", "mispBait", "schunaName")
ADDRESS_PROC = 242700455


def address_fields_strict(tik):
    """Raw address fields for the tik from procedure 242700455, WITHOUT
    permit_feed.address_of's None-tolerance: a failed/unparseable response
    raises ValueError (counted as a failure, retried on the next run) while
    a genuine empty result stores empty fields. A failure must never be
    persisted as "no address" - that would clear a good legacy address and
    skip the retry (#452 review)."""
    rows = _feed.call(
        ADDRESS_PROC, {"systemId": _feed.SYS, "tikNum": tik}
    )
    if rows is None:
        raise ValueError(f"proc {ADDRESS_PROC}: no usable response")
    if not isinstance(rows, list):
        # An error object or any other shape is a failed call, not "the tik
        # has no address" - only an empty list is a genuine no-row result.
        raise ValueError(
            f"proc {ADDRESS_PROC}: unexpected response shape {type(rows).__name__}"
        )
    if rows:
        r = rows[0]
        if not isinstance(r, dict):
            raise ValueError(f"proc {ADDRESS_PROC}: non-dict row {type(r).__name__}")
        return {
            "rehovName": str(r.get("rehovName") or "").strip(),
            "mispBait": str(r.get("mispBait") or "").strip(),
            "schunaName": str(r.get("schunaName") or "").strip(),
        }
    return {"rehovName": "", "mispBait": "", "schunaName": ""}


def data_fingerprint(payload):
    """Binds a checkpoint to the exact data generation it enriched: if the
    data file is replaced (e.g. a weekly refresh lands mid-backfill), a
    stale checkpoint must not skip re-enrichment."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def has_house_number(address):
    """A house number is a digit sequence; neighborhood-only strings (#408)
    like "קטמון הישנה" have none."""
    return any(ch.isdigit() for ch in address or "")


def needs_backfill(row):
    """Rows whose rendered address could change once raw fields exist:
    raw fields absent AND (address empty OR address with no house number).
    Rows already showing a real street address render identically (#452)."""
    if "rehovName" in row:
        return False
    address = (row.get("address") or "").strip()
    return not address or not has_house_number(address)


def select_targets(rows):
    """Tik numbers needing backfill, in stable feed order."""
    return [r["tik_num"] for r in rows if needs_backfill(r)]


def apply_fields(row, fields):
    """Feed semantics (#408): store the raw fields exactly as sourced and
    re-derive the joined address the same way a fresh scan would. An empty
    source yields empty fields - never a guessed address."""
    row.update({k: (fields.get(k) or "") for k in RAW_FIELDS})
    row["address"] = street_address(fields)


def load_checkpoint(path, fingerprint):
    """Tiks already enriched in an earlier run of THE SAME data generation.
    A missing/garbage file - or a checkpoint written against a different
    data file (e.g. a weekly refresh landed mid-backfill) - means a fresh
    start (reported, not fatal); a stale checkpoint must never skip
    re-enrichment of replaced rows."""
    try:
        with open(path, encoding="utf-8") as fh:
            cp = json.load(fh)
        if cp.get("data_sha256") != fingerprint:
            print("checkpoint was written against a different data file (fresh start)")
            return set()
        done = cp.get("done") or []
        print(f"checkpoint: resuming with {len(done)} tiks already done")
        return set(done)
    except FileNotFoundError:
        return set()
    except (json.JSONDecodeError, AttributeError):
        print("checkpoint read failed (fresh start)")
        return set()


def save_checkpoint(path, done, fingerprint):
    payload = {
        "checkpoint": True,
        "kind": "permit-address-backfill",
        "data_sha256": fingerprint,
        "done": sorted(done),
    }
    _atomic_write(path, payload)


def flush_data(path, payload):
    _atomic_write(path, payload)


def _atomic_write(path, payload):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/permit_requests.json")
    ap.add_argument("--checkpoint-file", default="data/.address-backfill-checkpoint.json")
    ap.add_argument("--limit", type=int, default=0, help="cap target count (0 = all)")
    ap.add_argument("--flush-every", type=int, default=25)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print target counts only")
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload["requests"]

    already_raw = sum(1 for r in rows if "rehovName" in r)
    legacy = [r for r in rows if "rehovName" not in r]
    empty = sum(1 for r in legacy if not (r.get("address") or "").strip())
    no_number = sum(
        1
        for r in legacy
        if (r.get("address") or "").strip() and not has_house_number(r["address"])
    )
    targets = select_targets(rows)
    print(
        f"rows {len(rows)}; raw fields present {already_raw}; empty address {empty}; "
        f"no house number {no_number}; backfill targets {len(targets)}"
    )
    if args.dry_run:
        return 0

    if args.limit:
        targets = targets[: args.limit]
    fingerprint = data_fingerprint(payload)
    done = load_checkpoint(args.checkpoint_file, fingerprint) if args.resume else set()
    pending = [t for t in targets if t not in done]
    print(f"targets {len(targets)}; pending after checkpoint {len(pending)}")

    by_tik = {r["tik_num"]: r for r in rows}
    enriched = failures = consecutive_failures = 0
    for i, tik in enumerate(pending, 1):
        time.sleep(PACE_SECONDS)
        try:
            fields = address_fields_strict(tik)
        except (RuntimeError, PermissionError):
            # anti-bot challenge or access denied: stop immediately, no
            # workaround - progress is durable via the flush/checkpoint.
            flush_data(args.data, payload)
            save_checkpoint(args.checkpoint_file, done, fingerprint)
            print(f"access wall at tik {tik} - stopped after {enriched} enriched")
            return 2
        except Exception as exc:  # noqa: BLE001 - one bad tik must not kill the batch (#399 pattern)
            failures += 1
            consecutive_failures += 1
            print(f"tik {tik}: address fetch failed ({exc}) - counted, continuing")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                # systemic failure (tunnel down, endpoint broken) looks like
                # per-tik failures; never report a failed run as done.
                flush_data(args.data, payload)
                save_checkpoint(args.checkpoint_file, done, fingerprint)
                print(
                    f"{consecutive_failures} consecutive failures - aborting; "
                    f"enriched {enriched}, NOT done"
                )
                return 1
            continue
        consecutive_failures = 0
        apply_fields(by_tik[tik], fields)
        done.add(tik)
        enriched += 1
        if i % args.flush_every == 0:
            flush_data(args.data, payload)
            save_checkpoint(args.checkpoint_file, done, fingerprint)
            print(f"progress {i}/{len(pending)} (enriched {enriched}, failures {failures})")

    flush_data(args.data, payload)
    save_checkpoint(args.checkpoint_file, done, fingerprint)
    print(f"done: enriched {enriched}, failures {failures}, targets {len(targets)}")
    # Failed tiks are not in the checkpoint's done set, so --resume retries
    # them - but a partially failed batch must not report success.
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
