#!/usr/bin/env python3
"""Probe the Jerusalem municipality public permit API (jerbasicserviceapi,
behind the public ykpubdata.jerusalem.muni.il viewer) through the
owner-operated L2TP tunnel. Fixed battery of candidate request shapes for
ONE parcel (gush 30025, helka 126) and ONE known request number.

Logs only fixed classification fields. No bodies, no IPs, no personal data.
Exit 0 = at least one shape served JSON data; 2 = challenge (stop);
1 = nothing usable.
"""
import json, subprocess, sys, time

IFACE = "ppp43"
BASE = "https://jerbasicserviceapi.jerusalem.muni.il/api"
PACE_S = 5
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
PAYLOAD = json.dumps({"misparTik": None, "gush": "30025", "helka": "126",
                      "rehovCode": None, "rehovName": None, "mispBait": None,
                      "mezahe": None, "migrash": None, "systemId": "26400046"})

CALLS = [
    ("POST", "/Rishui/SearchBakashot", PAYLOAD),
    ("POST", "/Rishui/Search", PAYLOAD),
    ("POST", "/Rishui/SearchTik", PAYLOAD),
    ("POST", "/SearchRishui", PAYLOAD),
    ("GET", "/Rishui/BakashalInfo?TikNum=1993/0664.03&SystemCode=26400046", None),
    ("GET", "/Details?TikNum=1993/0664.03&SystemCode=26400046&Page=BakashalInfo", None),
]
CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")


def probe(method, path, payload):
    cmd = ["curl", "-s", "-o", "/tmp/permit_probe_body", "-w", "%{http_code}\t%{content_type}\t%{size_download}",
           "-m", "45", "--interface", IFACE, "-X", method,
           "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
           "-H", "Origin: https://ykpubdata.jerusalem.muni.il",
           "-A", UA]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", payload]
    cmd.append(BASE + path)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        parts = out.stdout.split("\t")
        code, ctype, size = (parts + ["", "", "0"])[:3]
    except Exception as e:
        return {"call": method + " " + path, "result": "error", "error_kind": type(e).__name__}
    try:
        body = open("/tmp/permit_probe_body", "rb").read()
    except OSError:
        body = b""
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        return {"call": method + " " + path, "result": "anti_bot_challenge", "http": code}
    denied = b"access denied" in low
    is_json = "json" in (ctype or "") or body[:1] in (b"{", b"[")
    return {"call": method + " " + path,
            "result": "access_denied" if denied else "served",
            "http": code, "content_type": (ctype or "").split(";")[0],
            "bytes": int(size or 0), "json_like": bool(is_json)}


def main():
    usable = []
    for method, path, payload in CALLS:
        r = probe(method, path, payload)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        if r["result"] == "anti_bot_challenge":
            print(json.dumps({"status": "stopped", "reason": "challenge_detected"}), flush=True)
            return 2
        if r["result"] == "served" and r.get("json_like") and r.get("http") == "200" and r.get("bytes", 0) > 200:
            usable.append(r["call"])
        time.sleep(PACE_S)
    print(json.dumps({"status": "done", "usable_calls": usable}), flush=True)
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
