#!/usr/bin/env python3
"""Publication probe: does the Jerusalem municipality public permit API
(jerbasicserviceapi, backend of the public ykpubdata viewer) expose any
publication / objection-notice data for one specific public permit request
(1993/0664.03, Alfasi 9)? Refs #53.

Calls the viewer's own process/decision/condition procedures (recovered
from the viewer's published JS bundle) through the owner-operated L2TP
tunnel, slow-paced (4s between calls), and emits typed public-field
allowlists. Raw rows,
HTML, free-text notes, staff and payment fields are never logged. Refs #858.

Exit codes: 0 = all calls served JSON; 2 = anti-bot challenge/throttle
(stop, no workaround); 1 = anything else.
"""

import json
import math
import os
import re
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
# Fail closed on schema drift. No raw-value truncation or nested values.
# Text is restricted to public street/neighborhood labels. Process labels,
# notes, HTML, people lists and financial fields have no output route.
PUBLIC_FIELDS = {
    "details_242700447": {
        "tikNum": "tik",
        "statusCode": "number",
        "taarihStatus": "date",
        "fullTaarihStatus": "date",
    },
    "process_titles_242700448": {"processCode": "number"},
    "process_content_242700451": {
        "processCode": "number",
        "stepCode": "number",
        "planDateStr": "date",
        "execDateStr": "date",
        "taarihChasifa": "date",
        "taarihDiun": "date",
        "taarihTokefHahlata": "date",
    },
    "decisions_242700453": {},  # Unverified schema: counts only.
    "decisions_242700457": {
        "tikNum": "tik",
        "tohnit": "plan",
        "status_code": "number",
        "taarihStatus": "date",
    },
    "conditions_titles_242700449": {"tnaiCode": "number"},
    "conditions_content_242700450": {
        "tikNum": "tik",
        "tnaiCode": "number",
        "sugCode": "number",
        "answerCode": "number",
        "taarihBizua": "date",
        "taarihIdkun": "date",
    },
    "address_242700455": {
        "tikNum": "tik",
        "rehovCode": "number",
        "rehovName": "label",
        "mispBait": "house",
        "schunaCode": "number",
        "schunaName": "label",
        "cordinataX": "number",
        "cordinataY": "number",
    },
}
PATTERNS = {
    "tik": re.compile(r"[0-9]{4}/[0-9]{1,8}(?:\.[0-9]{1,4})?"),
    "date": re.compile(
        r"(?:[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}"
        r"(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,7})?Z?)?)"
    ),
    "plan": re.compile(r"[0-9A-Za-z\u05d0-\u05ea /.-]{1,40}"),
    "house": re.compile(r"[0-9\u05d0-\u05ea /.-]{1,16}"),
    "label": re.compile(r"[A-Za-z\u05d0-\u05ea0-9 '.,/()-]{1,80}"),
}
MAX_ROWS = 1000
CHALLENGE_MARKERS = (
    b"incapsula",
    b"recaptcha",
    b"captcha",
    b"_challenge",
    b"px-captcha",
    b"perimeterx",
    b"request blocked",
)


def _public_scalar(value, kind):
    if value is None:
        return True
    if kind == "number":
        return (
            type(value) in (int, float)
            and abs(value) <= 10**12
            and math.isfinite(value)
        )
    return isinstance(value, str) and PATTERNS[kind].fullmatch(value) is not None


def sanitize(rows, tag):
    """Project approved public fields only; never return raw/partial input."""
    fields = PUBLIC_FIELDS.get(tag, {})
    candidates = rows if isinstance(rows, list) else [rows]
    return [
        {
            key: value
            for key, value in row.items()
            if key in fields and _public_scalar(value, fields[key])
        }
        for row in candidates[:MAX_ROWS]
        if isinstance(row, dict)
    ]


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
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    parts = out.stdout.split("\t")
    code, ctype, size = (parts + ["", "", "0"])[:3]
    with open("/tmp/permit_pub_body", "rb") as f:
        body = f.read()
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
        except (ValueError, RecursionError):
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
                "rows": sanitize(rows, tag) if is_json else None,
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
