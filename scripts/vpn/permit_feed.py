#!/usr/bin/env python3
"""Permit-request feed pilot (issue #57): scan a bounded batch of council
parcels against the Jerusalem municipality public permit API
(jerbasicserviceapi, backend of the public ykpubdata viewer) through the
owner-operated L2TP tunnel, and write data/permit_requests.json.

Per request found, the process-step procedures (titles 242700448, content
242700451) supply the s.149 publication dates ("תחילת פרסום בפועל" /
"השלמת פרסום") - process metadata with no personal data. The details
procedure (which carries baaleiInyanList personal data) is NOT called.
Search-level + process-level fields only, DRAFT pilot, manual dispatch
only, slow pacing, stop on any anti-bot challenge (exit 2, no workaround).

Usage: python3 scripts/vpn/permit_feed.py [--limit 60] [--offset 0]
"""
import argparse
import base64
import datetime
import json
import os
import subprocess
import sys
import time

IFACE = "ppp43"
URL = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
SYS = "26400046"  # Rishui (permit licensing)
PACE_SECONDS = 3.0
MAX_CONSECUTIVE_FAILURES = 5
CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")
PUB_START_STEP = "תחילת פרסום בפועל"
PUB_END_STEP = "השלמת פרסום"
CHECKPOINT_BRANCH = "scan-checkpoint"  # issue #155: survives runner loss


def gh_api(method, path, token, payload=None):
    """Minimal GitHub REST call over the normal network (never the tunnel)."""
    cmd = ["curl", "-s", "-X", method, "-m", "30",
           "-H", f"Authorization: Bearer {token}",
           "-H", "Accept: application/vnd.github+json",
           "-H", "X-GitHub-Api-Version: 2022-11-28"]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    cmd.append(f"https://api.github.com{path}")
    r = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                       capture_output=True, text=True, timeout=45)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def checkpoint_payload(requests, offset, limit, done):
    return {"checkpoint": True,
            "note": "mid-batch scan checkpoint (issue #155); scratch branch, not a publish candidate",
            "batch": {"offset": offset, "limit": limit, "done": done},
            "requests": sorted(requests.values(), key=lambda r: r["tik_num"])}


def _push_checkpoint_once(requests, offset, limit, done, token, slug):
    """Commit the partial scan to the checkpoint branch (contents API), so a
    lost runner leaves progress behind. Return whether GitHub confirmed it."""
    try:
        ref = gh_api("GET", f"/repos/{slug}/git/ref/heads/{CHECKPOINT_BRANCH}", token)
        if not ref or "object" not in ref:
            main_ref = gh_api("GET", f"/repos/{slug}/git/ref/heads/main", token)
            sha = main_ref["object"]["sha"]
            gh_api("POST", f"/repos/{slug}/git/refs", token,
                   {"ref": f"refs/heads/{CHECKPOINT_BRANCH}", "sha": sha})
        cur = gh_api("GET", f"/repos/{slug}/contents/data/permit_requests.json"
                             f"?ref={CHECKPOINT_BRANCH}", token)
        body = {"message": f"Scan checkpoint {done}/{limit} at offset {offset}",
                "content": base64.b64encode(
                    json.dumps(checkpoint_payload(requests, offset, limit, done),
                               ensure_ascii=False, indent=1).encode()).decode(),
                "branch": CHECKPOINT_BRANCH}
        if cur and cur.get("sha"):
            body["sha"] = cur["sha"]
        r = gh_api("PUT", f"/repos/{slug}/contents/data/permit_requests.json", token, body)
        ok = bool(r and r.get("commit"))
        print(f"checkpoint pushed ({done}/{limit}): {'ok' if ok else 'FAILED'}")
        return ok
    except Exception as exc:
        print(f"checkpoint push failed: {exc}")
        return False


def push_checkpoint(requests, offset, limit, done, token, slug):
    """Require a confirmed durable commit before doing more scan/detail work."""
    for attempt in range(3):
        if _push_checkpoint_once(requests, offset, limit, done, token, slug):
            return
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise RuntimeError("checkpoint persistence failed after 3 attempts; stopping safely")


def load_checkpoint(token, slug):
    try:
        r = gh_api("GET", f"/repos/{slug}/contents/data/permit_requests.json"
                           f"?ref={CHECKPOINT_BRANCH}", token)
        if r and r.get("content"):
            return json.loads(base64.b64decode(r["content"]))
    except Exception as exc:
        print(f"checkpoint read failed (fresh start): {exc}")
    return None


def resume_start(cp, offset, limit, batch_len):
    """Parcels already scanned per the checkpoint, or 0 when it does not
    match this run's range."""
    b = (cp or {}).get("batch", {})
    if cp and cp.get("checkpoint") and b.get("offset") == offset \
            and b.get("limit") == limit and 0 < b.get("done", 0) <= batch_len:
        return b["done"]
    return 0


def call(proc, params):
    payload = json.dumps({"Cnn": "cnnGisYk", "ProcName": proc, "Parameters": params})
    cmd = ["curl", "-s", "-o", "/tmp/permit_feed_body", "-w", "%{http_code}",
           "-m", "45", "--interface", IFACE,
           "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
           "-H", "Content-Type: application/json",
           "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
           "--data", payload, URL]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    body = open("/tmp/permit_feed_body", "rb").read()
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        raise RuntimeError("anti_bot_challenge")
    if b"access denied" in low:
        raise PermissionError("access_denied")
    try:
        return json.loads(body)
    except Exception:
        return None


def ddmmyyyy(raw):
    raw = (raw or "").strip()
    try:
        d, m, y = raw.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except Exception:
        return ""


def publication_dates(tik):
    rows = call(242700451, {"SystemID": SYS, "TikNum": tik}) or []
    start = end = ""
    for r in rows if isinstance(rows, list) else []:
        step = r.get("stepCodeText") or ""
        if PUB_START_STEP in step:
            start = ddmmyyyy(r.get("execDateStr")) or ddmmyyyy(r.get("planDateStr"))
        elif PUB_END_STEP in step:
            end = ddmmyyyy(r.get("execDateStr")) or ddmmyyyy(r.get("planDateStr"))
    return start, end


def address_of(tik):
    rows = call(242700455, {"systemId": SYS, "tikNum": tik}) or []
    if isinstance(rows, list) and rows:
        r = rows[0]
        parts = [x for x in (r.get("rehovName"), r.get("mispBait"), r.get("schunaName")) if x]
        return " ".join(str(x) for x in parts)
    return ""


def load_parcel_list(path, known):
    """Parcels from a JSON [[gush, helka], ...] file, restricted to the
    council parcel set, de-duplicated, in stable order."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {(int(g), int(h)) for g, h in raw}
    return sorted(out & known)


def prior_batch_cursor(path, default):
    """The feed's existing backfill cursor, so a re-check never moves it."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("batch") or default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", default="data/ginot_hair_parcels.geojson")
    ap.add_argument("--out", default="data/permit_requests.json")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--checkpoint", action="store_true",
                    help="push a checkpoint commit every --checkpoint-every parcels "
                         "(needs GH_TOKEN + GITHUB_REPOSITORY)")
    ap.add_argument("--resume", action="store_true",
                    help="resume from the checkpoint branch when its range matches")
    ap.add_argument("--checkpoint-every", type=int, default=15,
                    help="parcels between checkpoint pushes (owner spec: 10-20)")
    ap.add_argument("--parcel-list", default="",
                    help="JSON file [[gush, helka], ...]: scan exactly these parcels "
                         "(tiered re-check, issue #344). No checkpoint/resume, address "
                         "kept from the prior row, feed batch cursor left untouched.")
    args = ap.parse_args()
    list_mode = bool(args.parcel_list)

    with open(args.parcels, encoding="utf-8") as fh:
        gj = json.load(fh)
    parcels = set()
    for f in gj.get("features", []):
        p = f.get("properties", {})
        g, h = p.get("gush"), p.get("helka")
        if g and h:
            parcels.add((int(g), int(h)))
    parcels = sorted(parcels)
    if list_mode:
        batch = load_parcel_list(args.parcel_list, set(parcels))
    else:
        batch = parcels[args.offset:args.offset + args.limit]
        # keep the known active parcel (Alfasi 9) in every pilot batch
        if (30025, 126) in parcels and (30025, 126) not in batch:
            batch.insert(0, (30025, 126))
    print(f"{len(parcels)} unique parcels, scanning batch of {len(batch)}")

    slug = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    # List mode never touches the scan-checkpoint branch: it belongs to the
    # offset backfill and a re-check must not overwrite or resume from it.
    ckpt_on = bool(args.checkpoint and token and slug and not list_mode)
    if args.checkpoint and not ckpt_on:
        print("checkpoint requested but GH_TOKEN/GITHUB_REPOSITORY missing - off")

    # Reuse only complete details checked today for unchanged search metadata.
    # Active publication steps can change even without a status change, so old
    # days and legacy rows without a check timestamp must always refresh.
    today = datetime.date.today().isoformat()
    try:
        previous = {r["tik_num"]: r for r in json.load(open(args.out)).get("requests", [])
                    if r.get("tik_num")}
    except (FileNotFoundError, json.JSONDecodeError):
        previous = {}
    requests, failures = {}, 0
    start = 0
    if args.resume and token and slug and not list_mode:
        cp = load_checkpoint(token, slug)
        start = resume_start(cp, args.offset, args.limit, len(batch))
        if start:
            requests = {r["tik_num"]: r for r in cp.get("requests", []) if r.get("tik_num")}
            print(f"resuming from checkpoint: {start}/{len(batch)} parcels already scanned, "
                  f"{len(requests)} requests carried")
    for i in range(start, len(batch)):
        gush, helka = batch[i]
        if i:
            time.sleep(PACE_SECONDS)
        try:
            rows = call(242700437, {"misparTik": None, "gush": gush, "helka": helka,
                                    "rehovCode": None, "mispBait": None, "mezahe": None,
                                    "migrash": None, "systemId": SYS})
        except RuntimeError:
            print("anti-bot challenge - stopping (no workaround)")
            return 2
        except Exception as exc:
            rows = None
            print(f"parcel {gush}/{helka}: {exc}")
        if rows is None:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                print("aborting: repeated request failures")
                return 1
            continue
        failures = 0
        for r in rows if isinstance(rows, list) else []:
            tik = r.get("tik_num")
            if not tik or tik in requests:
                continue
            requests[tik] = {
                "tik_num": tik,
                "mahut": (r.get("mahut_bakasha") or "").strip(),
                "sugbakasha": (r.get("teurSugbakasha") or "").strip(),
                "status": (r.get("teurStatus") or "").strip(),
                "status_date": ddmmyyyy(r.get("taarih_status")),
                "gush": gush, "helka": helka,
            }
        if (i + 1) % 10 == 0:
            print(f"[{i+1}/{len(batch)}] {len(requests)} requests so far")
        if ckpt_on and (i + 1) % args.checkpoint_every == 0:
            push_checkpoint(requests, args.offset, args.limit, i + 1, token, slug)

    if ckpt_on:
        push_checkpoint(requests, args.offset, args.limit, len(batch), token, slug)
    print(f"found {len(requests)} unique requests; fetching process + address data")
    detailed_since_checkpoint = 0
    for j, tik in enumerate(sorted(requests)):
        row = requests[tik]
        prior = previous.get(tik, {})
        metadata = ("mahut", "sugbakasha", "status", "status_date")
        details = ("publication_start", "publication_end_planned", "address", "details_checked_on")
        if (prior.get("details_checked_on") == today
                and all(key in prior for key in details)
                and all(prior.get(key) == row.get(key) for key in metadata)):
            row.update({key: prior[key] for key in details})
        if row.get("details_checked_on") == today and all(key in row for key in details):
            continue  # today's complete read, from prior output or durable checkpoint
        if j:
            time.sleep(PACE_SECONDS)
        try:
            start, end = publication_dates(tik)
            requests[tik]["publication_start"] = start
            requests[tik]["publication_end_planned"] = end
            if list_mode and prior.get("address"):
                requests[tik]["address"] = prior["address"]  # address does not change
            else:
                time.sleep(PACE_SECONDS)
                requests[tik]["address"] = address_of(tik)
            requests[tik]["details_checked_on"] = today
        except RuntimeError:
            print("anti-bot challenge during detail fetch - stopping (no workaround)")
            return 2
        except Exception as exc:
            print(f"{tik}: detail fetch failed: {exc}")
        detailed_since_checkpoint += 1
        if ckpt_on and detailed_since_checkpoint >= args.checkpoint_every:
            push_checkpoint(requests, args.offset, args.limit, len(batch), token, slug)
            detailed_since_checkpoint = 0

    if ckpt_on:
        push_checkpoint(requests, args.offset, args.limit, len(batch), token, slug)

    # Union with the existing feed file (main's version, from checkout):
    # each batch scans only its parcel slice, and without this merge every
    # batch PR would DELETE the previous batches' rows. Freshly scanned
    # rows win per tik_num; unscanned rows carry over unchanged.
    carried = 0
    try:
        with open(args.out, encoding="utf-8") as fh:
            prev = json.load(fh).get("requests", [])
        for r in prev:
            if r.get("tik_num") and r["tik_num"] not in requests:
                requests[r["tik_num"]] = r
                carried += 1
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if carried:
        print(f"carried over {carried} requests from previous batches")

    batch_cursor = {"offset": args.offset, "limit": args.limit}
    if list_mode:
        batch_cursor = prior_batch_cursor(args.out, batch_cursor)
    payload = {"generated": datetime.date.today().isoformat(),
               "source": "Jerusalem municipality public permit viewer API (ykpubdata)",
               "batch": batch_cursor,
               "requests": sorted(requests.values(), key=lambda r: r["tik_num"])}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {len(requests)} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
