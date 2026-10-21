"""Probe v3: file-number variants for the archive/taba file procs."""
import json, os, time
import urllib.request

API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
OUT = "/tmp/muni_api_probe"
os.makedirs(OUT, exist_ok=True)

CALLS = [
    ("tabanum_1377753", 242700464, {"tikTabaNum": "1377753"}),
    ("tabanum_full", 242700464, {"tikTabaNum": "101-1377753"}),
    ("tiknum_466", 242700466, {"tikNum": "1377753"}),
    ("tiknum_466_full", 242700466, {"tikNum": "101-1377753"}),
    ("tiknum_467", 242700467, {"tikNum": "1377753"}),
    ("tiknum_471", 242700471, {"tikNum": "1377753"}),
    ("tiknum_472", 242700472, {"tikNum": "1377753"}),
    ("tiknum_480", 242700480, {"tikNum": "1377753"}),
    ("taba_gush_pad", 242700470, {"misparTaba": "", "gush": "030007", "helka": "31", "rehovCode": "", "mispBait": ""}),
    ("taba_by_num", 242700470, {"misparTaba": "1377753", "gush": "", "helka": "", "rehovCode": "", "mispBait": ""}),
    ("rishui_search", 242700437, {"misparTik": "", "gush": "30007", "helka": "31", "rehovCode": "", "mispBait": "", "mezahe": "", "migrash": "", "systemId": ""}),
]

for label, proc, params in CALLS:
    body = json.dumps({"ProcName": proc, "Cnn": "cnnGisYk", "Parameters": params}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Origin": "https://ykpubdata.jerusalem.muni.il",
        "Referer": "https://ykpubdata.jerusalem.muni.il/",
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except Exception as e:
        print(f"{label}: ERROR {e}", flush=True)
        continue
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    print(f"{label}: status={status} bytes={len(raw)} blocked={blocked} body={raw[:200]!r}", flush=True)
    if blocked:
        raise SystemExit("AKAMAI BLOCK - stopping per policy")
    with open(os.path.join(OUT, f"v3_{label}.json"), "wb") as f:
        f.write(raw)
    time.sleep(2)
print("DONE", flush=True)
