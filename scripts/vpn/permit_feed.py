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
import datetime
import json
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcels", default="data/ginot_hair_parcels.geojson")
    ap.add_argument("--out", default="data/permit_requests.json")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    with open(args.parcels, encoding="utf-8") as fh:
        gj = json.load(fh)
    parcels = set()
    for f in gj.get("features", []):
        p = f.get("properties", {})
        g, h = p.get("gush"), p.get("helka")
        if g and h:
            parcels.add((int(g), int(h)))
    parcels = sorted(parcels)
    batch = parcels[args.offset:args.offset + args.limit]
    # keep the known active parcel (Alfasi 9) in every pilot batch
    if (30025, 126) in parcels and (30025, 126) not in batch:
        batch.insert(0, (30025, 126))
    print(f"{len(parcels)} unique parcels, scanning batch of {len(batch)}")

    requests, failures = {}, 0
    for i, (gush, helka) in enumerate(batch):
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

    print(f"found {len(requests)} unique requests; fetching process + address data")
    for j, tik in enumerate(sorted(requests)):
        if j:
            time.sleep(PACE_SECONDS)
        try:
            start, end = publication_dates(tik)
            requests[tik]["publication_start"] = start
            requests[tik]["publication_end_planned"] = end
            time.sleep(PACE_SECONDS)
            requests[tik]["address"] = address_of(tik)
        except RuntimeError:
            print("anti-bot challenge during detail fetch - stopping (no workaround)")
            return 2
        except Exception as exc:
            print(f"{tik}: detail fetch failed: {exc}")

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

    payload = {"generated": datetime.date.today().isoformat(),
               "source": "Jerusalem municipality public permit viewer API (ykpubdata)",
               "batch": {"offset": args.offset, "limit": args.limit},
               "requests": sorted(requests.values(), key=lambda r: r["tik_num"])}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {args.out}: {len(requests)} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
