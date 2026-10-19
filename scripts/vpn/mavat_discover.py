#!/usr/bin/env python3
"""Mavat endpoint discovery probe (runs through the owner-operated L2TP tunnel).

Fetches a fixed battery of candidate public endpoints for one tracked plan and
classifies each response into a small set of fixed categories. Logs only the
classification fields (no bodies, no headers beyond content-type, no IPs), so
no document content or secret material can leak into the public workflow log.

Exit codes: 0 = at least one endpoint served usable plan data;
2 = anti-bot challenge / throttling detected (stop, no workaround);
1 = nothing usable (all shell/error).
"""
import json, subprocess, sys, time

IFACE = "ppp43"
BASE = "https://mavat.iplan.gov.il"
PLAN_NUMBER = "101-1214279"
MP_ID = "1005303784"
PACE_S = 5

CANDIDATES = [
    ("sv4_page", f"{BASE}/SV4/1/{MP_ID}/310"),
    ("sv4_print", f"{BASE}/SV4/2/{MP_ID}/310"),
    ("rest_plan_by_number", f"{BASE}/rest/api/Plans/GetPlanByIdNumber?idNumber={PLAN_NUMBER}"),
    ("rest_plan_by_id", f"{BASE}/rest/api/Plans/GetPlanById?id={MP_ID}"),
    ("rest_plan_attachments", f"{BASE}/rest/api/Attacments/GetPlanAttachments?planNumber={PLAN_NUMBER}"),
    ("rest_plan_documents", f"{BASE}/rest/api/Plans/GetPlanDocuments?planNumber={PLAN_NUMBER}"),
    ("sv3_plan_card", f"{BASE}/SV3/1/{MP_ID}/310"),
]

CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")


def probe(name, url):
    cmd = ["curl", "-s", "-o", "/tmp/probe_body", "-w", "%{http_code}\t%{content_type}\t%{size_download}",
           "-m", "45", "--interface", IFACE, "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        parts = out.stdout.split("\t")
        code, ctype, size = (parts + ["", "", "0"])[:3]
    except Exception as e:
        return {"endpoint": name, "result": "error", "error_kind": type(e).__name__}
    try:
        body = open("/tmp/probe_body", "rb").read()
    except OSError:
        body = b""
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        return {"endpoint": name, "result": "anti_bot_challenge", "http": code}
    is_json = "json" in (ctype or "") or body[:1] in (b"{", b"[")
    doc_markers = sum(1 for m in (b"\xd7\x9e\xd7\xa1\xd7\x9e\xd7\x9b", b"Attacment", b"documents") if m in body)
    return {"endpoint": name, "result": "served", "http": code,
            "content_type": (ctype or "").split(";")[0], "bytes": int(size or 0),
            "json_like": bool(is_json), "doc_markers": doc_markers}


def main():
    results = []
    for name, url in CANDIDATES:
        r = probe(name, url)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        if r["result"] == "anti_bot_challenge":
            print(json.dumps({"status": "stopped", "reason": "challenge_detected"}), flush=True)
            return 2
        time.sleep(PACE_S)
    usable = [r for r in results if r["result"] == "served" and (r.get("json_like") or r.get("doc_markers"))]
    print(json.dumps({"status": "done", "usable_endpoints": [r["endpoint"] for r in usable]}), flush=True)
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
