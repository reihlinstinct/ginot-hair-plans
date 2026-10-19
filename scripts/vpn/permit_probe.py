#!/usr/bin/env python3
"""Single-call probe of the Jerusalem municipality public permit API
(jerbasicserviceapi), through the owner-operated L2TP tunnel, using the
EXACT call shape the public ykpubdata viewer itself makes (recovered from
the viewer's published JS bundle, no browser capture needed):

  POST /api/Db/ExecuteGetJSON
  {"Cnn":"cnnGisYk","ProcName":242700437,
   "Parameters":{"misparTik":null,"gush":30025,"helka":126,"rehovCode":null,
                 "mispBait":null,"mezahe":null,"migrash":null,
                 "systemId":"26400046"}}

242700437 is the viewer's Rishui (permit) search procedure; 26400046 is the
Rishui system id. One parcel, one call. Logs only fixed classification
fields plus result count and field NAMES (no personal data, no bodies).

Exit codes: 0 = API served JSON; 2 = anti-bot challenge/throttle (stop,
no workaround); 1 = anything else (access denied, error, non-JSON).
"""
import json, subprocess, sys

IFACE = "ppp43"
URL = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
PAYLOAD = json.dumps({
    "Cnn": "cnnGisYk",
    "ProcName": 242700437,
    "Parameters": {"misparTik": None, "gush": 30025, "helka": 126,
                   "rehovCode": None, "mispBait": None, "mezahe": None,
                   "migrash": None, "systemId": "26400046"},
})
CHALLENGE_MARKERS = (b"incapsula", b"recaptcha", b"captcha", b"_challenge",
                     b"px-captcha", b"perimeterx", b"request blocked")


DETAILS_PAYLOAD = json.dumps({
    "Cnn": "cnnGisYk",
    "ProcName": 242700447,
    "Parameters": {"tikNum": "1993/0664.03", "systemCode": "26400046"},
})


def call(payload, tag):
    cmd = ["curl", "-s", "-o", "/tmp/permit_probe_body", "-w", "%{http_code}\t%{content_type}\t%{size_download}",
           "-m", "45", "--interface", IFACE,
           "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
           "-H", "Content-Type: application/json",
           "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
           "--data", payload, URL]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    parts = out.stdout.split("\t")
    code, ctype, size = (parts + ["", "", "0"])[:3]
    body = open("/tmp/permit_probe_body", "rb").read()
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        print(json.dumps({"call": tag, "result": "anti_bot_challenge", "http": code}))
        return 2
    denied = b"access denied" in low
    is_json = "json" in (ctype or "") or body[:1] in (b"{", b"[")
    rows, keys = None, None
    if is_json:
        try:
            data = json.loads(body)
            rows = len(data) if isinstance(data, list) else None
            if isinstance(data, list) and data and isinstance(data[0], dict):
                keys = sorted(data[0].keys())
            elif isinstance(data, dict):
                keys = sorted(data.keys())
        except Exception:
            pass
    print(json.dumps({"call": tag, "result": "served" if not denied else "access_denied",
                      "http": code, "bytes": int(size or 0), "json_like": bool(is_json),
                      "row_count": rows, "field_names": keys}, ensure_ascii=False))
    return 0 if (not denied and is_json) else 1


def main():
    rc = call(PAYLOAD, "search_242700437")
    if rc == 0:
        import time
        time.sleep(5)
        rc = call(DETAILS_PAYLOAD, "details_242700447")
    return rc


if __name__ == "__main__":
    sys.exit(main())
