"""Read-only probe of the Jerusalem municipality public SPA API
(jerbasicserviceapi) through the owner-operated VPN tunnel.

This is the exact API the public ykpubdata.jerusalem.muni.il React app
calls in the browser. Public data only, no login. Any hard block
(Akamai Access Denied / challenge) is recorded and stops that request;
we never retry with rotated headers.
"""
import json, os, sys, time
import urllib.request

API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
OUT = "/tmp/muni_api_probe"
os.makedirs(OUT, exist_ok=True)

CALLS = [
    # archive content of a specific file (getArchivContentData in the SPA)
    ("archiv_content_26400046", 242700452, {"sysId": "26400046", "tikNum": "1377753"}),
    ("archiv_content_26400056", 242700571, {"sysId": "26400056", "tikNum": "1377753"}),
    # archive info by tik+system (ArchivInfo route)
    ("archiv_info", 242700447, {"tikNum": "1377753", "systemCode": "26400046"}),
    ("archiv_info_alt", 242700448, {"SystemID": "26400046", "TikNum": "1377753"}),
    # taba-file search by gush/helka (user asked: gush 30007 helka 31-33)
    ("taba_by_gush_helka_31", 242700470, {"misparTaba": "", "gush": "30007", "helka": "31", "rehovCode": "", "mispBait": ""}),
    ("taba_by_gush_helka_32", 242700470, {"misparTaba": "", "gush": "30007", "helka": "32", "rehovCode": "", "mispBait": ""}),
    ("taba_by_gush_helka_33", 242700470, {"misparTaba": "", "gush": "30007", "helka": "33", "rehovCode": "", "mispBait": ""}),
]

report = []
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
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except Exception as e:
        report.append({"label": label, "proc": proc, "error": str(e)[:200]})
        print(f"{label}: ERROR {e}", flush=True)
        continue
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    entry = {"label": label, "proc": proc, "status": status, "bytes": len(raw), "akamai_block": bool(blocked)}
    if not blocked and status == 200:
        fn = os.path.join(OUT, f"{label}.json")
        with open(fn, "wb") as f:
            f.write(raw)
        try:
            j = json.loads(raw)
            entry["rows"] = len(j) if isinstance(j, list) else "obj"
            entry["preview"] = json.dumps(j, ensure_ascii=False)[:600]
        except Exception:
            entry["preview"] = raw[:300].decode("utf-8", "replace")
    report.append(entry)
    print(f"{label}: status={status} bytes={len(raw)} blocked={blocked}", flush=True)
    time.sleep(2)  # gentle pacing, same as a human clicking through

with open(os.path.join(OUT, "api_probe_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print("DONE", flush=True)
