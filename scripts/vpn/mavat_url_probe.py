#!/usr/bin/env python3
"""One-shot experiment: which Attacments URL shape actually serves a plan
background document? The page's own clicks issue eid=<ID-space>&fn=<truncated>
(no edn/pn) for decision docs; background docs 404 on every guessed combo so
far. Opens the public SV4 plan page (establishes the same session the page
uses), then in-page fetches a small candidate matrix for ONE doc and reports
status/ctype/bytes per candidate. Public doc, same session as the page."""

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

OUT = Path("/tmp/mavat_url_probe")
OUT.mkdir(parents=True, exist_ok=True)

PLAN = "101-1377753"
MP_ID = "1005407450"
SV4 = f"https://mavat.iplan.gov.il/SV4/1/{MP_ID}/310"
BASE = "https://mavat.iplan.gov.il"

# doc under test: נספח בינוי
DOC_ID = "1001136679037"  # rsPlanDocsGen ID
DOC_ATT = "1000036366767"  # rsPlanDocsGen ATTACHMENT_ID
DOC_NAME = "בינוי"
DOC_INFO = "נספח בינוי\r\nמחייב לעניין מיקום, שימושים, נסיגות ושימור - חתום להפקדה"


def trunc_bytes(s, n):
    """Truncate like the page seems to: cut the UTF-8 string at n bytes."""
    return s.encode("utf-8")[:n].decode("utf-8", errors="ignore")


fns = [
    f"{PLAN}_{DOC_NAME}",
    f"{PLAN}_{DOC_NAME}_",
    f"{PLAN}_{DOC_NAME}.pdf",
    f"{PLAN}_מסמכי רקע לתכנית_{DOC_NAME}",
    f"{PLAN}_מסמכים מופקדים_{DOC_NAME}",
    trunc_bytes(f"{PLAN}_{DOC_NAME}_{DOC_INFO.splitlines()[0]}", 51),
    trunc_bytes(f"{PLAN}_{DOC_NAME}_{DOC_INFO.splitlines()[0]}", 45),
    "",
    "x",
]
CANDS = []
for eid in (DOC_ID, DOC_ATT):
    for fn in fns:
        CANDS.append((eid, fn, False))  # no edn/pn (page-issued shape)
CANDS.append((DOC_ID, f"{PLAN}_{DOC_NAME}", True))  # with edn/pn
CANDS.append((DOC_ATT, f"{PLAN}_{DOC_NAME}", True))


def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="he-IL",
        )
        page = ctx.new_page()
        page.goto(SV4, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        time.sleep(3)
        text = page.inner_text("body") if page.query_selector("body") else ""
        if "מטרת התכנית" not in text and MP_ID not in text:
            print("plan page did not load - aborting", flush=True)
            browser.close()
            return 1
        for eid, fn, with_edn in CANDS:
            url = f"{BASE}/rest/api/Attacments/?eid={eid}&fn={quote(fn)}"
            if with_edn:
                url += f"&edn=temp-default&pn={PLAN}"
            try:
                res = page.evaluate(
                    """async (url) => {
                  const r = await fetch(url, {credentials: 'include'});
                  const b = await r.arrayBuffer();
                  const u8 = new Uint8Array(b.slice(0, 16));
                  return {status: r.status,
                          ctype: r.headers.get('content-type') || '',
                          bytes: b.byteLength,
                          head: Array.from(u8)};
                }""",
                    url,
                )
            except Exception as exc:
                res = {"error": type(exc).__name__}
            head = bytes(res.get("head", []))
            kind = (
                "PDF"
                if head[:4] == b"%PDF"
                else "ZIP"
                if head[:2] == b"PK"
                else "other"
            )
            row = {
                "eid": eid,
                "fn": fn[:40],
                "edn": with_edn,
                "status": res.get("status"),
                "ctype": (res.get("ctype") or "")[:40],
                "bytes": res.get("bytes"),
                "kind": kind,
            }
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kind == "PDF" and res.get("status") == 200:
                # fetch the full body and save it
                full = page.evaluate(
                    """async (url) => {
                  const r = await fetch(url, {credentials: 'include'});
                  const b = await r.arrayBuffer();
                  const u8 = new Uint8Array(b);
                  let s = '';
                  for (let i = 0; i < u8.length; i += 65536) {
                    s += String.fromCharCode.apply(null, u8.subarray(i, i + 65536));
                  }
                  return btoa(s);
                }""",
                    url,
                )
                import base64

                (
                    OUT / f"binguy_{eid}_{'edn' if with_edn else 'plain'}.pdf"
                ).write_bytes(base64.b64decode(full))
                print(f"SAVED binguy_{eid}.pdf", flush=True)
            time.sleep(1.5)
        browser.close()
    with open(OUT / "probe_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
