"""Probe v2: discover the public SPA's dropdown chains, then re-query.

Same public read-only API the ykpubdata React app calls. Low rate (2s
between calls), hard stop recorded on any block. No CAPTCHA, no retries
with rotated headers.
"""
import json, os, time
import urllib.request

API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
OUT = "/tmp/muni_api_probe"
os.makedirs(OUT, exist_ok=True)

def call(label, proc, params):
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
        return None
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    print(f"{label}: status={status} bytes={len(raw)} blocked={blocked}", flush=True)
    if blocked:
        raise SystemExit("AKAMAI BLOCK - stopping per policy")
    with open(os.path.join(OUT, f"v2_{label}.json"), "wb") as f:
        f.write(raw)
    time.sleep(2)
    try:
        return json.loads(raw)
    except Exception:
        return None

# 1. dropdown roots
systems = call("systems_242700424", 242700424, {})
list2 = call("list_242700426", 242700426, {})

# 2. whatever system codes exist, fetch their next-level lists
codes = set()
for data in (systems, list2):
    if isinstance(data, list):
        for row in data[:20]:
            if isinstance(row, dict):
                for k, v in row.items():
                    if isinstance(v, (int, str)) and ("ode" in k or "ystem" in k or "id" in k.lower()):
                        codes.add(str(v))
print("candidate system codes:", sorted(codes)[:20], flush=True)
for c in sorted(codes)[:10]:
    call(f"per_system_242700427_{c}", 242700427, {"systemCode": c})

# 3. archive procs against every candidate system code for TikNum 1377753
for c in sorted(codes)[:10]:
    call(f"archivinfo_242700447_{c}", 242700447, {"tikNum": "1377753", "systemCode": c})
    call(f"archivcontent_242700452_{c}", 242700452, {"sysId": c, "tikNum": "1377753"})

# 4. taba search by gush/helka with int and string types
for gh in (("30007", "31"), (30007, 31), ("30007", "32"), ("30007", "33")):
    call(f"taba_{gh[0]}_{gh[1]}", 242700470,
         {"misparTaba": "", "gush": gh[0], "helka": gh[1], "rehovCode": "", "mispBait": ""})
print("DONE", flush=True)
