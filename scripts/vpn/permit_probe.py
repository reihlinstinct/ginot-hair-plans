#!/usr/bin/env python3
"""Single-call probe of the Jerusalem municipality public permit API
(jerbasicserviceapi), through the owner-operated L2TP tunnel.

Fetches ONE public request-detail endpoint for one parcel (gush 30025,
helka 126) and logs only fixed classification fields. No bodies, no IPs,
no personal data in the log.

Exit codes: 0 = API served JSON; 2 = anti-bot challenge/throttle (stop,
no workaround); 1 = anything else (access denied, error, non-JSON).
"""
import json, subprocess, sys

IFACE = "ppp43"
URL = "https://jerbasicserviceapi.jerusalem.muni.il/api/Rishui/BakashalInfo?gush=30025&helka=126"
CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")


def main():
    cmd = ["curl", "-s", "-o", "/tmp/permit_probe_body", "-w", "%{http_code}\t%{content_type}\t%{size_download}",
           "-m", "45", "--interface", IFACE,
           "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
           "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", URL]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        parts = out.stdout.split("\t")
        code, ctype, size = (parts + ["", "", "0"])[:3]
    except Exception as e:
        print(json.dumps({"result": "error", "error_kind": type(e).__name__}))
        return 1
    try:
        body = open("/tmp/permit_probe_body", "rb").read()
    except OSError:
        body = b""
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        print(json.dumps({"result": "anti_bot_challenge", "http": code}))
        return 2
    denied = b"access denied" in low
    is_json = "json" in (ctype or "") or body[:1] in (b"{", b"[")
    print(json.dumps({"result": "served" if not denied else "access_denied",
                      "http": code, "content_type": (ctype or "").split(";")[0],
                      "bytes": int(size or 0), "json_like": bool(is_json)}))
    return 0 if (not denied and is_json) else 1


if __name__ == "__main__":
    sys.exit(main())
