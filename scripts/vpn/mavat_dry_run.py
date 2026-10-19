"""Mavat dry-run probe: does mavat.iplan.gov.il serve a public plan page via the VPN?

Public documents only. No login. No CAPTCHA solving or bypass: if the response
is an anti-bot interstitial or a hard challenge, this script classifies it and
exits non-zero so the workflow stops and reports instead of working around it.

Exit codes: 0 = plan page served; 2 = anti-bot challenge/interstitial (stop);
3 = blocked / soft-404 / other failure.
"""
from __future__ import annotations
import json
import subprocess
import sys

URL = "https://mavat.iplan.gov.il/SV4/1/1005303784/310"  # public plan page (Gymnasium 101-1214279)
DEVICE = "ppp43"

CHALLENGE_MARKERS = [
    "_Incapsula_Resource", "Incapsula incident", "x-iinfo",
    "px-captcha", "PerimeterX", "Pardon Our Interruption",
    "Access to this page has been denied", "Request unsuccessful. Incapsula",
    "cdn-cgi/challenge", "cf-chl",
]
SHELL_MARKERS = ["מידע תכנוני", "SV4", "main.", "app-root", "iplan"]
SOFT404_MARKERS = ['<html dir="rtl" lang="he-IL" class="no-js">']


def run_curl() -> tuple[int, str, dict]:
    cmd = [
        "curl", "-sS", "-L", "--max-time", "40",
        "--interface", DEVICE,
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "-o", "/tmp/mavat_dry_run_body.html",
        "-w", "%{http_code}",
        "-D", "/tmp/mavat_dry_run_headers.txt",
        URL,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if p.returncode:
        return -1, "", {"curl_exit": p.returncode}
    status = int(p.stdout.strip() or "0")
    body = open("/tmp/mavat_dry_run_body.html", encoding="utf-8", errors="replace").read()
    headers = {}
    try:
        for line in open("/tmp/mavat_dry_run_headers.txt", encoding="utf-8", errors="replace"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return status, body, headers


def main() -> None:
    try:
        status, body, headers = run_curl()
    except Exception as error:  # noqa: BLE001 - redact to a fixed class
        print(json.dumps({"result": "error", "class": type(error).__name__}, ensure_ascii=False), flush=True)
        raise SystemExit(3) from None

    # Never log response bodies or IP addresses: only fixed classifications.
    safe_headers = {k: v for k, v in headers.items() if k in ("server", "content-type")}
    if status == -1:
        print(json.dumps({"result": "network_error", "headers": safe_headers}, ensure_ascii=False), flush=True)
        raise SystemExit(3)
    if any(m in body for m in CHALLENGE_MARKERS):
        print(json.dumps({"result": "anti_bot_challenge", "http": status,
                          "note": "interstitial/challenge detected; stopping, no bypass per policy",
                          "headers": safe_headers}, ensure_ascii=False), flush=True)
        raise SystemExit(2)
    if status == 200 and any(m in body for m in SHELL_MARKERS):
        print(json.dumps({"result": "plan_page_served", "http": status, "url_kind": "SV4 plan page",
                          "body_bytes": len(body.encode('utf-8', 'replace')),
                          "headers": safe_headers}, ensure_ascii=False), flush=True)
        raise SystemExit(0)
    if status in (404, 400) and any(m in body for m in SOFT404_MARKERS):
        print(json.dumps({"result": "soft_404_error_page", "http": status,
                          "note": "gov.il generic error page - likely edge/IP filtering",
                          "headers": safe_headers}, ensure_ascii=False), flush=True)
        raise SystemExit(3)
    print(json.dumps({"result": "unexpected_response", "http": status,
                      "body_bytes": len(body.encode('utf-8', 'replace')),
                      "headers": safe_headers}, ensure_ascii=False), flush=True)
    raise SystemExit(3)


if __name__ == "__main__":
    main()
