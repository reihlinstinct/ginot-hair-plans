"""Probe v4: Jerusalem ykpubdata public API for taba file 1158146 (plan 101-1158146).

Read-only POSTs to the public SPA API, same calls the public site makes.
Parameterized by env TIK_NUM (bare file number, no 101- prefix)."""

import http.client
import json
import os
import urllib.request

API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
OUT = "/tmp/muni_api_probe"
os.makedirs(OUT, exist_ok=True)
TIK = os.environ.get("TIK_NUM", "1158146")

CALLS = [
    ("plan_record_464", 242700464, {"tikTabaNum": TIK}),
    ("plan_card_466", 242700466, {"tikNum": TIK}),
    ("proc_467", 242700467, {"tikNum": TIK}),
    ("proc_471", 242700471, {"tikNum": TIK}),
    ("proc_472", 242700472, {"tikNum": TIK}),
    ("proc_480", 242700480, {"tikNum": TIK}),
    (
        "taba_by_num_470",
        242700470,
        {"misparTaba": TIK, "gush": "", "helka": "", "rehovCode": "", "mispBait": ""},
    ),
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
    except (OSError, http.client.HTTPException) as e:
        print(f"{label}: ERROR {e}", flush=True)
        continue
    with open(f"{OUT}/v4_{label}_{TIK}.json", "wb") as f:
        f.write(raw)
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    print(f"{label}: status={status} bytes={len(raw)} blocked={blocked}", flush=True)
