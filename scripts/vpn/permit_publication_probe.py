#!/usr/bin/env python3
"""Publication probe: does the Jerusalem municipality public permit API
(jerbasicserviceapi, backend of the public ykpubdata viewer) expose any
publication / objection-notice data for one specific public permit request
(1993/0664.03, Alfasi 9)? Refs #53.

Calls the viewer's own process/decision/condition procedures (recovered
from the viewer's published JS bundle) through the owner-operated L2TP
tunnel, slow-paced (4s between calls), and logs row VALUES with
personal-data fields stripped (baaleiInyanList, achraTikFullName).

Exit codes: 0 = all calls served JSON; 2 = anti-bot challenge/throttle
(stop, no workaround); 1 = anything else.
"""

import json
import os
import subprocess
import sys
import time

IFACE = "ppp43"
URL = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
# Probe target tik: PROBE_TIK env (workflow_dispatch input) overrides the
# default Alfasi 9 tik from #53. Format-guarded like the feed inputs.
TIK = os.environ.get("PROBE_TIK", "1993/0664.03")
assert "\n" not in TIK and '"' not in TIK and len(TIK) < 20, "bad PROBE_TIK"
SYS = "26400046"  # Rishui (permit licensing) system id in the viewer

PROCS = [
    ("details_242700447", 242700447, {"tikNum": TIK, "systemCode": SYS}),
    ("process_titles_242700448", 242700448, {"SystemID": SYS, "TikNum": TIK}),
    ("process_content_242700451", 242700451, {"SystemID": SYS, "TikNum": TIK}),
    ("decisions_242700453", 242700453, {"systemID": SYS, "tikNum": TIK}),
    ("decisions_242700457", 242700457, {"systemID": SYS, "tikNum": TIK}),
    ("conditions_titles_242700449", 242700449, {"TikNum": TIK}),
    ("conditions_content_242700450", 242700450, {"TikNum": TIK}),
    ("address_242700455", 242700455, {"systemId": SYS, "tikNum": TIK}),
]
STRIP_KEYS = {"baaleiInyanList", "achraTikFullName"}
CHALLENGE_MARKERS = (
    b"incapsula",
    b"recaptcha",
    b"captcha",
    b"_challenge",
    b"px-captcha",
    b"perimeterx",
    b"request blocked",
)
MAX_ROW_CHARS = 6000


def sanitize(rows):
    out = []
    for row in rows if isinstance(rows, list) else [rows]:
        if not isinstance(row, dict):
            out.append(row)
            continue
        clean = {k: v for k, v in row.items() if k not in STRIP_KEYS}
        s = json.dumps(clean, ensure_ascii=False, default=str)
        out.append(
            json.loads(s[:MAX_ROW_CHARS])
            if len(s) <= MAX_ROW_CHARS
            else {"_truncated": s[:MAX_ROW_CHARS]}
        )
    return out


def call(tag, proc, params):
    payload = json.dumps({"Cnn": "cnnGisYk", "ProcName": proc, "Parameters": params})
    cmd = [
        "curl",
        "-s",
        "-o",
        "/tmp/permit_pub_body",
        "-w",
        "%{http_code}\t%{content_type}\t%{size_download}",
        "-m",
        "45",
        "--interface",
        IFACE,
        "-H",
        "Referer: https://ykpubdata.jerusalem.muni.il/",
        "-H",
        "Content-Type: application/json",
        "-A",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "--data",
        payload,
        URL,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    parts = out.stdout.split("\t")
    code, ctype, size = (parts + ["", "", "0"])[:3]
    body = open("/tmp/permit_pub_body", "rb").read()
    low = body[:200000].lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        print(json.dumps({"call": tag, "result": "anti_bot_challenge", "http": code}))
        return 2
    denied = b"access denied" in low
    is_json = "json" in (ctype or "") or body[:1] in (b"{", b"[")
    rows = None
    if is_json:
        try:
            rows = json.loads(body)
        except Exception:
            is_json = False
    n = len(rows) if isinstance(rows, list) else (1 if isinstance(rows, dict) else 0)
    print(
        json.dumps(
            {
                "call": tag,
                "result": "served" if not denied else "access_denied",
                "http": code,
                "bytes": int(size or 0),
                "row_count": n,
                "rows": sanitize(rows) if is_json else None,
            },
            ensure_ascii=False,
        )
    )
    return 0 if (not denied and is_json) else 1


def main():
    rc = 0
    for i, (tag, proc, params) in enumerate(PROCS):
        if i:
            time.sleep(4)
        r = call(tag, proc, params)
        if r == 2:
            return 2
        rc = rc or r
    return rc


if __name__ == "__main__":
    sys.exit(main())
