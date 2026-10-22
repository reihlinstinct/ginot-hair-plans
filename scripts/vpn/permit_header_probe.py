#!/usr/bin/env python3
"""One-off: does the permit search API expose a change signal in its HTTP
response headers? One search request (same shape as permit_probe.py), then one
conditional repeat with If-Modified-Since. Logs ONLY allowlisted header
names/values and the status code. No body is logged. Stop on any challenge.
Exit: 0 ok, 2 anti-bot challenge, 1 other failure.
"""
import json
import subprocess
import sys
from pathlib import Path

IFACE = "ppp43"
URL = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
PAYLOAD = json.dumps({"Cnn": "cnnGisYk", "ProcName": 242700437, "Parameters": {
    "misparTik": None, "gush": 30025, "helka": 126, "rehovCode": None,
    "mispBait": None, "mezahe": None, "migrash": None, "systemId": "26400046"}})
ALLOW = ("date", "last-modified", "etag", "cache-control", "age", "expires",
         "content-type", "content-length", "vary", "accept-ranges")
CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")


def parse_headers(raw):
    """Status line + allowlisted headers from a curl -D dump (last response)."""
    blocks = [b for b in raw.replace("\r", "").strip().split("\n\n") if b.strip()]
    lines = blocks[-1].split("\n") if blocks else []
    status = lines[0] if lines else ""
    kept = {}
    for ln in lines[1:]:
        name, _, val = ln.partition(":")
        if name.strip().lower() in ALLOW:
            kept[name.strip().lower()] = val.strip()
    return {"status_line": status[:40], "headers": kept, "names_seen_count": len(lines) - 1}


def call(tag, extra):
    cmd = ["curl", "-s", "-D", "/tmp/hdr", "-o", "/tmp/body", "-m", "45", "--interface", IFACE,
           "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
           "-H", "Content-Type: application/json",
           "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
           *extra, "--data", PAYLOAD, URL]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    body = Path("/tmp/body").read_bytes()[:200000].lower()
    if any(m in body for m in CHALLENGE_MARKERS):
        print(json.dumps({"call": tag, "result": "anti_bot_challenge"}))
        return None
    info = parse_headers(Path("/tmp/hdr").read_text(encoding="latin-1"))
    info.update(call=tag, body_bytes=len(body))
    print(json.dumps(info, ensure_ascii=False))
    return info


def main():
    first = call("search", [])
    if first is None:
        return 2
    lm = first["headers"].get("last-modified") or first["headers"].get("date")
    if not lm:
        return 0
    second = call("conditional", ["-H", f"If-Modified-Since: {lm}"])
    return 2 if second is None else 0


if __name__ == "__main__":
    sys.exit(main())
