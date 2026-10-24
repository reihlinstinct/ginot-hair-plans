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

# Phase 2: download every document the archive listed, through the tunnel.
import time

DOCS_DIR = f"{OUT}/docs"
os.makedirs(DOCS_DIR, exist_ok=True)
content_path = f"{OUT}/v5_archiv_content_{TIK.replace('/', '-')}.json"
try:
    docs = json.load(open(content_path))
except Exception as e:
    print(f"doc-list parse: ERROR {e}", flush=True)
    docs = []

manifest = []
for i, d in enumerate(docs, 1):
    url = d.get("urlDoc")
    descr = d.get("documentDescr", "")
    if not url:
        continue
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://ykpubdata.jerusalem.muni.il/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raw, status, ctype = e.read(), e.code, ""
    except Exception as e:
        print(f"doc{i}: ERROR {e}", flush=True)
        manifest.append({"i": i, "descr": descr, "error": str(e)})
        continue
    ext = "dwfx" if d.get("docExtension") == "dwfx" else ("pdf" if "pdf" in ctype.lower() or raw[:5] == b"%PDF-" else "bin")
    fn = f"{i:02d}.{ext}"
    open(f"{DOCS_DIR}/{fn}", "wb").write(raw)
    blocked = b"Access Denied" in raw[:4000] and b"edgesuite" in raw[:4000]
    print(f"doc{i} [{descr}]: status={status} bytes={len(raw)} ctype={ctype} ext={ext} blocked={blocked}", flush=True)
    manifest.append({"i": i, "file": fn, "descr": descr, "dateIn": d.get("dateIn"), "status": status, "bytes": len(raw), "ctype": ctype, "blocked": blocked})
    time.sleep(1)

json.dump(manifest, open(f"{OUT}/v5_docs_manifest.json", "w"), ensure_ascii=False, indent=1)
