"""Probe v5: optical-archive (archiv) content for a Rishui permit tik.

Read-only POSTs to the public ykpubdata SPA API — the same calls the
public viewer itself makes (ArchivInfo / getArchivContentData), through
the owner-operated L2TP tunnel. Parameterized by env TIK_NUM (full permit
tik number, e.g. "2026/0439.00") and SYS_ID (default 26400046 = Rishui).
Hard stop is recorded, never worked around.
"""

import json
import os
import urllib.request

API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
OUT = "/tmp/muni_api_probe"
os.makedirs(OUT, exist_ok=True)
TIK = os.environ.get("TIK_NUM", "2026/0439.00")
SYS = os.environ.get("SYS_ID", "26400046")

CALLS = [
    ("archiv_info", 242700447, {"tikNum": TIK, "systemCode": SYS}),
    ("archiv_info_alt", 242700448, {"SystemID": SYS, "TikNum": TIK}),
    ("archiv_content", 242700452, {"sysId": SYS, "tikNum": TIK}),
    ("archiv_content_56", 242700571, {"sysId": "26400056", "tikNum": TIK}),
    ("permit_details", 242700438, {"tikNum": TIK, "systemCode": SYS}),
]

for label, proc, params in CALLS:
    body = json.dumps(
        {"ProcName": proc, "Cnn": "cnnGisYk", "Parameters": params}
    ).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Origin": "https://ykpubdata.jerusalem.muni.il",
            "Referer": "https://ykpubdata.jerusalem.muni.il/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except Exception as e:
        print(f"{label}: ERROR {e}", flush=True)
        continue
    safe_tik = TIK.replace("/", "-")
    open(f"{OUT}/v5_{label}_{safe_tik}.json", "wb").write(raw)
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    print(f"{label}: status={status} bytes={len(raw)} blocked={blocked}", flush=True)
    if blocked:
        raise SystemExit("AKAMAI BLOCK - stopping per policy")
