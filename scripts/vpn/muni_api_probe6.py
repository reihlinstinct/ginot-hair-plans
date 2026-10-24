"""Probe v6: retry the 4 archive items that 404'd in the v5 run."""
import os, urllib.request, time
OUT = "/tmp/muni_api_probe/docs_retry"
os.makedirs(OUT, exist_ok=True)
ITEMS = {
    6:  "11EE2007-F852-4DCB-BCE5-A1C02D391C10" and "9AB27F61-001C-4109-9AC8-38EB9EBDC67F",
    17: "D48BC4ED-2F41-4971-BA38-2FCC7D04B001",
    23: "139926DD-67AA-4187-83B1-1E693EA14405",
    24: "5D3BD126-6D0F-42D0-80A8-F3D6B714DB2A",
}
for i, guid in ITEMS.items():
    url = f"https://jerarchivews.jerusalem.muni.il/api/items/{guid}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://ykpubdata.jerusalem.muni.il/",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raw, status, ctype = e.read(), e.code, ""
    except Exception as e:
        print(f"doc{i}: ERROR {e}", flush=True); continue
    ext = "pdf" if raw[:5] == b"%PDF-" else ("dwfx" if raw[:4] == b"PK\x03\x04" else "bin")
    open(f"{OUT}/{i:02d}.{ext}", "wb").write(raw)
    print(f"doc{i}: status={status} bytes={len(raw)} ctype={ctype} ext={ext}", flush=True)
    time.sleep(1)
