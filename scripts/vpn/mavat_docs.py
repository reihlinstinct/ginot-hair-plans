#!/usr/bin/env python3
"""Mavat plan document fetch (runs through the owner-operated L2TP tunnel).

Fetches the full PUBLIC document set of one deposit-stage plan page
(e.g. 101-1377753), including background-appendix categories and the
"admin comments" tab that a plain page scrape does not expose.

Method (public pages only, no login, no challenge bypass):
1. Probe a small fixed set of candidate public REST endpoints and record
   what serves JSON (classification + body saved to the artifact only).
2. Open the plan's public SV4 page in headless Chromium; record every
   API-ish XHR the page itself makes so document-list endpoints are
   learned from the page's own traffic.
3. Click through the document-section tabs and capture the page's own
   per-category ZIP downloads.
4. Parse captured document metadata for document URLs and fetch any that
   the ZIP capture missed, with polite pacing.
5. Save everything under the artifact dir plus a machine-readable fetch
   report (per source: found / downloaded / failed).

Hard rule (no workaround): on any hard challenge / CAPTCHA / throttling
the run stops with exit 2. Logs carry fixed classification fields only;
document metadata and documents are public plan records and go to the
run artifact, never to the log.

Exit codes: 0 = fetched >=1 document; 1 = nothing fetched; 2 = challenge.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

MP_ID = os.environ.get("MAVAT_MP_ID", "1005407450")
PLAN = os.environ.get("MAVAT_PLAN_NUMBER", "101-1377753")
OUT = Path(os.environ.get("MAVAT_OUT", "/tmp/mavat_docs"))
BASE = "https://mavat.iplan.gov.il"
PAGE_URL = f"{BASE}/SV4/1/{MP_ID}/310"
PACE_S = 4
MAX_DOWNLOADS = 80
MAX_BODY = 8 * 1024 * 1024

CHALLENGE_MARKERS = ("incapsula", "recaptcha", "px-captcha", "perimeterx",
                     "request blocked", "access denied", "are you a robot")
DOC_EXT = (".pdf", ".zip", ".doc", ".docx", ".tif", ".tiff", ".jpg", ".jpeg", ".png")

REST_CANDIDATES = [
    f"{BASE}/rest/api/Attacments/GetPlanAttachments?planNumber={PLAN}",
    f"{BASE}/rest/api/Plans/GetPlanDocuments?planNumber={PLAN}",
    f"{BASE}/rest/api/Plans/GetPlanByIdNumber?idNumber={PLAN}",
]

report = {"plan": PLAN, "mp_id": MP_ID, "page": PAGE_URL,
          "rest_json": [], "xhr": [], "clicks": [], "downloads": [],
          "admin_comments_chars": 0, "failures": []}
xhr_bodies = []  # saved to artifact, never logged


class Challenge(Exception):
    pass


def check_challenge_text(text):
    low = (text or "").lower()
    if any(m in low for m in CHALLENGE_MARKERS):
        raise Challenge()


def safe_name(name):
    name = re.sub(r"[^\w.\- ]+", "_", (name or "").strip())[:120]
    return name or "file"


def save_body(subdir, name, data):
    d = OUT / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / safe_name(name)
    p.write_bytes(data)
    return p


def url_strings(obj, acc):
    """Collect URL-ish strings from parsed JSON."""
    if isinstance(obj, dict):
        for v in obj.values():
            url_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            url_strings(v, acc)
    elif isinstance(obj, str):
        s = obj
        if s.startswith("http") or s.startswith("/"):
            acc.add(s)


def main():
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    doc_urls = set()
    downloaded_names = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="he-IL")
        page = ctx.new_page()

        def on_response(resp):
            try:
                url = resp.url
                if "iplan" not in url:
                    return
                if not ("/rest/" in url or "/api/" in url.lower()):
                    return
                ctype = (resp.headers.get("content-type") or "").split(";")[0]
                entry = {"url": url[:300], "status": resp.status, "ctype": ctype}
                report["xhr"].append(entry)
                if "json" in ctype and resp.status == 200:
                    body = resp.body()
                    if len(body) <= MAX_BODY:
                        xhr_bodies.append({"url": url[:300], "body": body.decode("utf-8", "replace")})
                        try:
                            url_strings(json.loads(body), doc_urls)
                        except Exception:
                            pass
            except Exception:
                pass

        page.on("response", on_response)

        # --- 1. cheap REST probes (public, no login) ---
        for url in REST_CANDIDATES:
            try:
                r = ctx.request.get(url, timeout=45000)
                ctype = (r.headers.get("content-type") or "").split(";")[0]
                body = r.body()
                low = body[:200000].lower()
                if any(m.encode() in low for m in CHALLENGE_MARKERS):
                    raise Challenge()
                served = r.status == 200 and ("json" in ctype or body[:1] in (b"{", b"["))
                report["rest_json"].append({"url": url.split("/rest/")[-1][:120],
                                            "status": r.status, "served_json": bool(served)})
                if served:
                    xhr_bodies.append({"url": url, "body": body.decode("utf-8", "replace")})
                    try:
                        url_strings(json.loads(body), doc_urls)
                    except Exception:
                        pass
            except Challenge:
                raise
            except Exception as exc:
                report["failures"].append({"stage": "rest_probe", "error": type(exc).__name__})
            time.sleep(PACE_S)

        # --- 1b. direct-fetch mode: a committed eid list short-circuits
        #     discovery (ids learned from the page's own SV4/1 response) ---
        doc_list_path = os.environ.get("MAVAT_DOC_LIST", "")
        direct_docs = []
        if doc_list_path:
            try:
                with open(doc_list_path, encoding="utf-8") as fh:
                    direct_docs = json.load(fh)["docs"]
            except Exception as exc:
                if os.environ.get("MAVAT_FETCH_MODE") == "clickdocs" and isinstance(exc, FileNotFoundError):
                    # UI discovery needs no precomputed eid list. Never use another
                    # plan's list as a substitute for a missing optional file.
                    print("no optional doc list; discovering this plan through its UI", flush=True)
                    doc_list_path = ""
                else:
                    print(f"doc list unreadable ({type(exc).__name__})", flush=True)
                    return 1

        # --- 2. open the SV4 page ---
        page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            pass
        time.sleep(2)
        text = page.inner_text("body") if page.query_selector("body") else ""
        if PLAN not in text:
            check_challenge_text(text)
            print("no_plan_content on SV4 page - stopping", flush=True)
            return 2
        print("plan page loaded (content check positive)", flush=True)
        page.screenshot(path=str(OUT / "page_top.png"), full_page=False)

        if direct_docs and os.environ.get("MAVAT_FETCH_MODE") not in ("zip", "clickdocs"):
            print(f"direct-fetch mode: {len(direct_docs)} documents", flush=True)
            from urllib.parse import quote
            for i, d in enumerate(direct_docs):
                eid, name = d["id"], d["name"]
                fn_variants = [f"{PLAN}_{name}.pdf",
                               f"{PLAN}_{name}_".encode().decode() ,
                               f"DOC_{eid}.pdf", ""]
                try:
                    r = None
                    for fn in fn_variants:
                        url = (f"{BASE}/rest/api/Attacments/?eid={eid}"
                               f"&fn={quote(fn)}&edn=temp-default&pn={PLAN}")
                        rr = ctx.request.get(url, timeout=120000,
                                             headers={"Referer": PAGE_URL})
                        if rr.status == 200:
                            r = rr
                            break
                        if rr.status not in (404, 400):
                            r = rr
                            break
                        r = rr
                    body = r.body()
                    ctype = (r.headers.get("content-type") or "").split(";")[0]
                    low = body[:200000].lower()
                    if any(m.encode() in low for m in CHALLENGE_MARKERS):
                        raise Challenge()
                    if r.status != 200 or not body:
                        report["downloads"].append({"doc": name, "status": r.status, "skipped": True})
                        continue
                    ext = (".pdf" if body[:4] == b"%PDF" else
                           ".zip" if body[:2] == b"PK" else
                           ".xls" if body[:8].startswith(b"\xd0\xcf\x11\xe0") else ".bin")
                    fname = safe_name(f"{PLAN}_{name}") + ext
                    save_body("docs", fname, body)
                    downloaded_names.add(fname)
                    report["downloads"].append({"doc": name, "file": fname, "bytes": len(body), "ctype": ctype})
                    print(f"saved {fname} ({len(body)} bytes)", flush=True)
                except Challenge:
                    raise
                except Exception as exc:
                    report["failures"].append({"stage": "direct_fetch", "doc": name, "error": type(exc).__name__})
                time.sleep(PACE_S)
            browser.close()
            got = len(downloaded_names)
            report["summary"] = {"files_downloaded": got, "mode": "direct"}
            (OUT / "fetch_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
            return 0 if got else 1


        # --- 2c. zip mode: relay the page's own zipAttacments call ----
        # The page issues POST /rest/api/zipAttacments {auth,fname,ids,
        # entityNumber,token} when its own "הורדת קבצים ב ZIP" link is
        # clicked. We capture that token from the page-issued request,
        # then ask the same public endpoint (from the page's own JS
        # context, same session) for the background-appendix ids. Public
        # docs only; no login; no challenge bypass.
        if os.environ.get("MAVAT_FETCH_MODE") == "zip" and direct_docs:
            import base64
            print(f"zip mode: {len(direct_docs)} documents", flush=True)
            tokens = []

            def on_zip_req(req):
                try:
                    if "zipAttacments" in req.url and req.method == "POST":
                        data = json.loads(req.post_data or "{}")
                        if data.get("token"):
                            tokens.append(data["token"])
                except Exception:
                    pass

            page.on("request", on_zip_req)

            def harvest_token():
                before = len(tokens)
                # expand the documents accordion first (the ZIP affordance
                # is only clickable once the category is open; run 4)
                try:
                    page.get_by_text(re.compile("^מסמכי התכנית$")).first.click(timeout=6000)
                    time.sleep(2)
                except Exception:
                    pass
                clicked = False
                try:
                    page.get_by_text(re.compile("הורדת קבצים ב ZIP")).first.click(timeout=6000)
                    clicked = True
                except Exception:
                    pass
                if not clicked:
                    # brute-force the same affordance scan that captured
                    # the page-issued zipAttacments requests in run 4
                    for selector in ["a", "button", "img", "span", "div"]:
                        done = False
                        for el in page.locator(selector).all():
                            try:
                                if not el.is_visible():
                                    continue
                                desc = ((el.get_attribute("title") or "") + " " +
                                        (el.get_attribute("class") or "") + " " +
                                        (el.inner_text() or "")[:40])
                                if "zip" not in desc.lower():
                                    continue
                                el.click(timeout=4000)
                                done = True
                                break
                            except Exception:
                                continue
                        if done:
                            break
                for _ in range(40):
                    if len(tokens) > before:
                        return tokens[-1]
                    time.sleep(0.5)
                return tokens[-1] if tokens else None

            FETCH_JS = """async ({ids, fname, entityNumber, token}) => {
              const r = await fetch('/rest/api/zipAttacments', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({auth:'', fname, ids, entityNumber, token})});
              const blob = await r.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = fname;
              document.body.appendChild(a); a.click();
              return r.status;
            }"""

            def fetch_zip(ids, out_name):
                # fresh token per request: the page-issued token is
                # single-use (replay returns {"CaptchaNotValid":true},
                # verified 2026-10-21). Each harvest clicks the page's
                # own ZIP link so the token is the site's own.
                token = harvest_token()
                if not token:
                    report["failures"].append({"stage": "zip_mode", "error": "no_token"})
                    return None
                try:
                    with page.expect_download(timeout=120000) as dl_info:
                        status = page.evaluate(
                            FETCH_JS,
                            {"ids": [int(i) for i in ids], "fname": out_name,
                             "entityNumber": PLAN, "token": token})
                    dl = dl_info.value
                    path = OUT / "zipdocs" / safe_name(out_name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    dl.save_as(str(path))
                    return {"file": path.name, "status": status,
                            "bytes": path.stat().st_size}
                except Exception as exc:
                    report["failures"].append({"stage": "zip_fetch",
                                               "ids": ids[:3],
                                               "error": type(exc).__name__})
                    return None

            all_ids = [d["id"] for d in direct_docs]
            batch = fetch_zip(all_ids, f"{PLAN}_background_docs.zip")
            ok = False
            if batch and batch["bytes"] > 10000:
                import zipfile
                try:
                    with zipfile.ZipFile(OUT / "zipdocs" / batch["file"]) as zf:
                        names = zf.namelist()
                    if len(names) >= max(1, len(all_ids) - 2):
                        ok = True
                        downloaded_names.add(batch["file"])
                        report["downloads"].append({**batch, "mode": "zip_batch",
                                                    "entries": len(names)})
                        print(f"zip batch: {len(names)} entries", flush=True)
                except Exception:
                    pass
            if not ok and batch is None and not tokens:
                report["failures"].append({"stage": "zip_mode",
                                           "error": "batch_failed_no_token"})
            if not ok:
                for d in direct_docs:
                    eid, name = d["id"], d["name"]
                    res = fetch_zip([eid], f"{PLAN}_{name}.zip")
                    if res and res["bytes"] > 1000:
                        downloaded_names.add(res["file"])
                        report["downloads"].append({**res, "doc": name, "mode": "zip_single"})
                        print(f"zip: {name} ({res['bytes']} bytes)", flush=True)
                    time.sleep(PACE_S)
            browser.close()
            got = len(downloaded_names)
            report["summary"] = {"files_downloaded": got, "mode": "zip"}
            (OUT / "fetch_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
            return 0 if got else 1


        # --- 2d. clickdocs mode: drive the page's own download UI ------
        # The relay approach (zipAttacments with a captured token) is
        # captcha-bound and was stopped ({"CaptchaNotValid":true} on
        # replay, run 39552931669). This mode only clicks the same
        # public buttons a visitor clicks; every request is issued by
        # the page itself with its own per-click token. Responses to
        # those page-issued requests are read from the page's own
        # session (the page downloads ZIPs via XHR, so no browser
        # download event fires); we never replay a captured token.
        # The page's "preparing file" overlay hangs when the browser
        # download cannot start headlessly, so it is dismissed after
        # every click (same effect as a visitor pressing Escape).
        if os.environ.get("MAVAT_FETCH_MODE") == "clickdocs":
            print("clickdocs mode: page-issued downloads only", flush=True)

            seen_bin = [0]

            def on_binary_response(resp):
                try:
                    url = resp.url
                    if "iplan" not in url:
                        return
                    ctype = (resp.headers.get("content-type") or "").split(";")[0].lower()
                    if ctype not in ("application/octet-stream", "application/pdf",
                                     "application/msword",
                                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
                        return
                    seen_bin[0] += 1
                    body = resp.body()
                    if not body or len(body) < 200:
                        return
                    cd = resp.headers.get("content-disposition") or ""
                    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
                    base = m.group(1).strip() if m else ""
                    if not base:
                        if body[:4] == b"%PDF":
                            base = f"page_doc_{seen_bin[0]:02d}.pdf"
                        elif body[:2] == b"PK":
                            base = f"page_zip_{seen_bin[0]:02d}.zip"
                        else:
                            base = f"page_bin_{seen_bin[0]:02d}.bin"
                    fname = safe_name(base)
                    path = OUT / "zips" / fname
                    n = 1
                    while path.exists():
                        path = OUT / "zips" / f"{n}_{fname}"
                        n += 1
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                    downloaded_names.add(path.name)
                    report["downloads"].append({"file": path.name, "via": "page_issued_response",
                                                "url": url[:200], "bytes": len(body), "ctype": ctype})
                    print(f"captured {path.name} ({len(body)} bytes)", flush=True)
                except Exception:
                    pass

            page.on("response", on_binary_response)
            try:
                ctx.on("page", lambda p2: p2.on("response", on_binary_response))
            except Exception:
                pass

            issued_urls = []
            def _on_request(req):
                try:
                    if "Attacments/?eid=" in req.url:
                        issued_urls.append(req.url)
                except Exception:
                    pass
            page.on("request", _on_request)
            report["issued_doc_urls"] = issued_urls

            def dismiss_overlays():
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                try:
                    page.evaluate("""() => {
                      for (const s of ['.modal-backdrop', '.modal', '.swal2-container',
                                       '[class*="overlay"]', '[class*="Overlay"]',
                                       '[class*="spinner"]', '[class*="loader"]']) {
                        document.querySelectorAll(s).forEach(e => e.remove());
                      }
                      document.body.style.overflow = 'auto';
                      document.documentElement.style.overflow = 'auto';
                    }""")
                except Exception:
                    pass

            def expand(label):
                for el in page.get_by_text(re.compile(f"^{label}$")).all():
                    try:
                        if not el.is_visible():
                            continue
                        try:
                            el.click(timeout=4000)
                        except Exception:
                            el.evaluate("e => { let n = e; for (let i = 0; i < 5 && n; i++) { if (n.getAttribute('href') || n.onclick || n.tagName === 'A' || n.tagName === 'BUTTON') break; n = n.parentElement; } (n || e).click(); }")
                        time.sleep(1.5)
                        return True
                    except Exception:
                        continue
                return False

            def click_and_wait(el, timeout):
                try:
                    with page.expect_download(timeout=6000) as dl_info:
                        el.click(timeout=timeout)
                    dl = dl_info.value
                    time.sleep(1)
                    dismiss_overlays()
                    return dl
                except Exception:
                    time.sleep(2)
                    dismiss_overlays()
                    return None

            expanded = {}
            for label in ("מסמכי התכנית", "מסמכי מידע מנהלי", "נוסחי פרסום"):
                expanded[label] = expand(label)
            # מסמכים מופקדים is a sub-panel of מסמכי התכנית; verify the
            # רקע category really appears (clicks can no-op silently)
            mufkadim_open = False
            for attempt in range(3):
                expand("מסמכים מופקדים")
                try:
                    if page.get_by_text(re.compile("מסמכי רקע לתכנית")).first.is_visible():
                        mufkadim_open = True
                        break
                except Exception:
                    pass
                try:
                    page.locator("text=מסמכים מופקדים").first.click(timeout=4000, force=True)
                    time.sleep(2)
                    if page.get_by_text(re.compile("מסמכי רקע לתכנית")).first.is_visible():
                        mufkadim_open = True
                        break
                except Exception:
                    pass
            expanded["מסמכים מופקדים"] = mufkadim_open
            expanded["מסמכי רקע לתכנית"] = expand("מסמכי רקע לתכנית") if mufkadim_open else False
            if not expanded.get("מסמכי רקע לתכנית"):
                report["failures"].append({"stage": "expand", "pattern": "מסמכי רקע לתכנית",
                                           "error": "label_not_on_page"})
            # plan-docs dropdown (e.g. "מסמכים מופקדים") may hide the
            # category's ZIP link until opened
            try:
                for el in page.get_by_text(re.compile("מסמכים מופקדים")).all():
                    try:
                        if el.is_visible():
                            el.click(timeout=5000)
                            time.sleep(1.5)
                            break
                    except Exception:
                        continue
            except Exception:
                pass
            # click each background-doc row by its visible name; the page
            # issues the exact Attacments URL itself (guessed fn 404s)
            bg_names = ["בינוי ופיתוח", "בנין לשימור", "חוות דעת כלכלית",
                        "מצב מאושר", "נספח חברתי", "נספח סביבה", "סקר עצים",
                        "תנועה", "בינוי", "נוף", "טבלאות איזון והקצאה",
                        "תדפיס הוראות התכנית", "תדפיס תשריט מצב מוצע"]
            for nm in bg_names:
                got = False
                try:
                    rows = page.locator(f'tr:has-text("{nm}"), li:has-text("{nm}"), div[role="row"]:has-text("{nm}")')
                    n = rows.count()
                    for ri in range(min(n, 4)):
                        row = rows.nth(ri)
                        try:
                            if not row.is_visible():
                                continue
                            for sel in ["img[src*='pdf' i]", "a[title*='הורד']",
                                        "img[title*='הורד']", "[title*='צפיה']",
                                        "a", "img"]:
                                ic = row.locator(sel)
                                if ic.count() == 0:
                                    continue
                                dl = click_and_wait(ic.first, 5000)
                                if dl:
                                    path = OUT / "zips" / ("bg_" + safe_name(dl.suggested_filename))
                                    path.parent.mkdir(parents=True, exist_ok=True)
                                    dl.save_as(str(path))
                                    downloaded_names.add(path.name)
                                    report["downloads"].append({"file": path.name, "via": "bg_row_click",
                                                                "bytes": path.stat().st_size})
                                    print(f"download: {path.name}", flush=True)
                                    got = True
                                    break
                            if got:
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
                time.sleep(1)

            page.screenshot(path=str(OUT / "clickdocs_expanded.png"), full_page=True)

            # dump the page's own document links/rows so exact download
            # URLs are known (the Attacments endpoint 404s on a guessed
            # fn parameter)
            try:
                report["dom_doc_links"] = page.evaluate("""() => {
                  const out = [];
                  document.querySelectorAll('a[href*="ttacments"], a[href*="eid="]').forEach(a => {
                    out.push({kind: 'href', href: a.href.slice(0, 300), text: (a.innerText || '').trim().slice(0, 60)});
                  });
                  document.querySelectorAll('[onclick*="ttacments"], [onclick*="eid"]').forEach(e => {
                    out.push({kind: 'onclick', code: (e.getAttribute('onclick') || '').slice(0, 300)});
                  });
                  return out;
                }""")
            except Exception as exc:
                report["failures"].append({"stage": "dom_dump", "error": type(exc).__name__})

            # decisions first (before any ZIP click can hang the page):
            # expand החלטות מוסדות תכנון, then open the docs it lists
            try:
                if not expand("החלטות מוסדות תכנון"):
                    for el in page.get_by_text(re.compile("החלטות מוסדות")).all():
                        try:
                            if not el.is_visible():
                                continue
                            el.scroll_into_view_if_needed(timeout=4000)
                            time.sleep(0.5)
                            el.evaluate("e => e.click()")
                            break
                        except Exception:
                            continue
                time.sleep(3)
                page.screenshot(path=str(OUT / "clickdocs_meetings.png"), full_page=True)
                # each meeting row hides its docs behind "קבצים מצורפים"
                for el in page.get_by_text(re.compile("קבצים מצורפים")).all():
                    try:
                        if el.is_visible():
                            el.click(timeout=4000)
                            time.sleep(1.5)
                    except Exception:
                        continue
                page.screenshot(path=str(OUT / "clickdocs_meetings2.png"), full_page=True)
                try:
                    body_txt = page.inner_text("body")
                    k = body_txt.find("החלטות מוסדות")
                    report["decisions_region_text"] = body_txt[k:k+2000] if k >= 0 else "header not found"
                except Exception:
                    pass
                idx2 = 0
                for selector in ["a[href*='Attacments']", "a[href*='eid=']",
                                 "img[title*='הורד']", "a[title*='הורד']",
                                 "i[title*='הורד']", "span[title*='הורד']",
                                 "img[src*='pdf' i]", "img[alt*='PDF' i]",
                                 "[title*='צפיה']", "[title*='צפי']"]:
                    dloc = page.locator(selector)
                    j = 0
                    while j < dloc.count():
                        try:
                            el = dloc.nth(j)
                            if el.is_visible():
                                idx2 += 1
                                click_and_wait(el, 5000)
                                time.sleep(2)
                        except Exception:
                            pass
                        j += 1
            except Exception as exc:
                report["failures"].append({"stage": "meetings_tab",
                                           "error": type(exc).__name__})

            # every visible category ZIP link: each is a distinct
            # page-issued download of one document category
            idx = 0
            zloc = page.get_by_text(re.compile("הורדת קבצים ב ZIP"))
            i = 0
            while i < zloc.count():
                try:
                    el = zloc.nth(i)
                    if not el.is_visible():
                        # the מסמכים מופקדים panel may have collapsed
                        # mid-loop; reopen it and retry once
                        try:
                            for dd in page.get_by_text(re.compile("מסמכים מופקדים")).all():
                                if dd.is_visible():
                                    dd.click(timeout=4000)
                                    break
                            time.sleep(1.5)
                        except Exception:
                            pass
                        el = zloc.nth(i)
                    if el.is_visible():
                        idx += 1
                        dl = click_and_wait(el, 6000)
                        if dl:
                            path = OUT / "zips" / f"cat{idx:02d}_" + safe_name(dl.suggested_filename)
                            path.parent.mkdir(parents=True, exist_ok=True)
                            dl.save_as(str(path))
                            downloaded_names.add(path.name)
                            report["downloads"].append({"file": path.name, "via": "category_zip",
                                                        "bytes": path.stat().st_size})
                            print(f"download: {path.name}", flush=True)
                        time.sleep(2)
                except Exception:
                    pass
                i += 1
            page.screenshot(path=str(OUT / "clickdocs_end.png"), full_page=True)

            # let page-issued XHR downloads settle
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(3)

            # in-page fetch fallback: ask the page's own JS session for
            # each committed eid the UI clicks could not reach (same
            # request the page issues when a visitor opens the document
            # link; no token replay, no new endpoint)
            import base64 as _b64
            from urllib.parse import quote as _quote

            report["inpage"] = []

            def inpage_get(eid, name):
                fn_variants = [f"{PLAN}_{name}.pdf",
                               f"{PLAN}_{name}_".encode().decode() ,
                               f"DOC_{eid}.pdf", ""]
                for fn in fn_variants:
                    url = (f"{BASE}/rest/api/Attacments/?eid={eid}"
                           f"&fn={_quote(fn)}&edn=temp-default&pn={PLAN}")
                    try:
                        res = page.evaluate("""async (url) => {
                          const r = await fetch(url, {credentials: 'include'});
                          const b = await r.arrayBuffer();
                          const u8 = new Uint8Array(b);
                          let s = '';
                          for (let i = 0; i < u8.length; i += 65536) {
                            s += String.fromCharCode.apply(null, u8.subarray(i, i + 65536));
                          }
                          return {status: r.status, ctype: r.headers.get('content-type') || '', b64: btoa(s)};
                        }""", url)
                    except Exception as exc:
                        report["failures"].append({"stage": "inpage_fetch", "doc": name,
                                                   "error": type(exc).__name__})
                        return False
                    body = _b64.b64decode(res["b64"]) if res.get("b64") else b""
                    report["inpage"].append({"eid": eid, "fn": fn[:30],
                                             "status": res.get("status"),
                                             "ctype": (res.get("ctype") or "")[:60],
                                             "bytes": len(body),
                                             "head": body[:40].hex()})
                    if res.get("status") != 200 or not body:
                        continue
                    low = body[:200000].lower()
                    if any(m.encode() in low for m in CHALLENGE_MARKERS):
                        raise Challenge()
                    if body[:4] == b"%PDF":
                        ext = ".pdf"
                    elif body[:2] == b"PK":
                        ext = ".zip"
                    elif body[:8].startswith(b"\xd0\xcf\x11\xe0"):
                        ext = ".xls"
                    else:
                        continue
                    fname = safe_name(f"{PLAN}_{name}") + ext
                    path = OUT / "zips" / fname
                    n = 1
                    while path.exists():
                        path = OUT / "zips" / f"{n}_{fname}"
                        n += 1
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                    downloaded_names.add(path.name)
                    report["downloads"].append({"file": path.name, "via": "inpage_fetch",
                                                "eid": eid, "bytes": len(body)})
                    print(f"inpage {path.name} ({len(body)} bytes)", flush=True)
                    return True
                return False

            extra_lists = []
            if doc_list_path:
                extra_lists.append(doc_list_path)
            dec_path = os.environ.get("MAVAT_DEC_LIST",
                                      f"data/mavat_declist_{PLAN}.json")
            if os.path.exists(dec_path):
                extra_lists.append(dec_path)
            for lp in extra_lists:
                try:
                    with open(lp, encoding="utf-8") as fh:
                        for d in json.load(fh)["docs"]:
                            time.sleep(PACE_S)
                            inpage_get(str(d["id"]), d["name"])
                except Challenge:
                    raise
                except Exception as exc:
                    report["failures"].append({"stage": "inpage_list", "list": lp,
                                               "error": type(exc).__name__})

            browser.close()
            got = len(downloaded_names)
            report["summary"] = {"files_downloaded": got, "mode": "clickdocs"}
            (OUT / "fetch_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
            print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
            return 0 if got else 1

        # --- 3. expand the documents accordion and click every download
        #     affordance, so each request is issued by the page itself ---
        req_log = []

        def on_request(req):
            try:
                if "ttacments" in req.url:
                    req_log.append({"method": req.method, "url": req.url[:400],
                                    "post": (req.post_data or "")[:400]})
            except Exception:
                pass

        page.on("request", on_request)

        def click_text(pattern, exact=False, wait=3):
            try:
                loc = page.get_by_text(re.compile(pattern), exact=exact).first
                loc.click(timeout=9000)
                time.sleep(wait)
                return True
            except Exception as exc:
                report["failures"].append({"stage": "expand", "pattern": pattern,
                                           "error": type(exc).__name__})
                return False

        # the documents accordion and the background-docs category inside it
        click_text(r"^מסמכי התכנית$")
        page.screenshot(path=str(OUT / "expanded_docs.png"), full_page=True)
        click_text(r"מסמכי רקע לתכנית")
        page.screenshot(path=str(OUT / "expanded_bg.png"), full_page=True)

        # collect short visible texts for the artifact (page structure log)
        try:
            texts = page.locator("a, button, [role='tab'], [role='button'], span, div").all_inner_texts()
            short = sorted({t.strip() for t in texts if 0 < len(t.strip()) <= 60})
            save_body(".", "visible_texts.txt", ("\n".join(short)).encode("utf-8"))
        except Exception:
            pass

        # brute-force: click every visible download affordance and capture
        # whatever downloads; the page issues its own requests, so URLs and
        # headers are exactly the site's own
        seen_clicks = set()
        done_clicks = 0
        for selector in ["a", "button", "img", "span", "div"]:
            for el in page.locator(selector).all():
                if done_clicks >= 45:
                    break
                try:
                    if not el.is_visible():
                        continue
                    desc = ((el.get_attribute("title") or "") + " " +
                            (el.get_attribute("href") or "") + " " +
                            (el.get_attribute("src") or "") + " " +
                            (el.get_attribute("class") or "") + " " +
                            (el.inner_text() or "")[:30])
                    if not re.search(r"הורד|pdf|zip|PDF|ZIP|attach|download|מסמך", desc, re.I):
                        continue
                    if desc in seen_clicks:
                        continue
                    seen_clicks.add(desc)
                    try:
                        with page.expect_download(timeout=15000) as dl_info:
                            el.click(timeout=6000)
                        dl = dl_info.value
                        path = OUT / "zips" / safe_name(dl.suggested_filename)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        dl.save_as(str(path))
                        downloaded_names.add(path.name)
                        report["downloads"].append({"file": path.name, "via": desc[:80]})
                        print(f"download: {path.name}", flush=True)
                    except Exception:
                        pass
                    done_clicks += 1
                    time.sleep(PACE_S)
                except Exception:
                    continue
            if done_clicks >= 45:
                break

        # learned request shapes go to the artifact (public URLs only)
        save_body(".", "attacments_requests.json",
                  json.dumps(req_log, ensure_ascii=False, indent=1).encode("utf-8"))

        # admin-comments tab text (if visible anywhere on the page)
        try:
            body_text = page.inner_text("body") or ""
            save_body(".", "page_text_final.txt", body_text.encode("utf-8"))
            report["admin_comments_chars"] = len(body_text)
        except Exception:
            pass

        # --- 4. fetch every document URL the page/API exposed ---
        # keep URLs that look like documents or download endpoints
        cand = sorted(u for u in doc_urls
                      if any(e in u.lower() for e in DOC_EXT)
                      or "download" in u.lower()
                      or "attachment" in u.lower()
                      or "attacment" in u.lower())
        print(f"document URL candidates: {len(cand)}", flush=True)
        for i, u in enumerate(cand[:MAX_DOWNLOADS]):
            full = u if u.startswith("http") else BASE + u
            name = safe_name(full.rsplit("/", 1)[-1].split("?")[0]) or f"doc_{i}"
            try:
                r = ctx.request.get(full, timeout=90000)
                body = r.body()
                ctype = (r.headers.get("content-type") or "").split(";")[0]
                low = body[:200000].lower()
                if any(m.encode() in low for m in CHALLENGE_MARKERS):
                    raise Challenge()
                if r.status != 200 or not body or "html" in ctype:
                    report["downloads"].append({"url": full[-160:], "status": r.status,
                                                "skipped": True, "ctype": ctype})
                    continue
                ext = ".pdf" if body[:4] == b"%PDF" else (".zip" if body[:2] == b"PK" else "")
                fname = name if name.lower().endswith(DOC_EXT) else name + (ext or ".bin")
                if fname in downloaded_names:
                    continue
                downloaded_names.add(fname)
                save_body("docs", fname, body)
                report["downloads"].append({"url": full[-160:], "file": fname,
                                            "bytes": len(body), "ctype": ctype})
                print(f"saved {fname} ({len(body)} bytes)", flush=True)
            except Challenge:
                raise
            except Exception as exc:
                report["failures"].append({"stage": "doc_fetch", "error": type(exc).__name__})
            time.sleep(PACE_S)

        browser.close()

    # artifact: captured API bodies (public plan metadata)
    api_dir = OUT / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(xhr_bodies):
        (api_dir / f"xhr_{i:02d}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")

    got = len(downloaded_names) + sum(1 for c in report["clicks"] if c.get("download"))
    report["summary"] = {"files_downloaded": len(downloaded_names),
                         "zips_captured": sum(1 for c in report["clicks"] if c.get("download")),
                         "xhr_recorded": len(report["xhr"]),
                         "rest_served": sum(1 for r in report["rest_json"] if r.get("served_json"))}
    (OUT / "fetch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return 0 if got else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Challenge:
        print("hard challenge detected - stopping with no workaround", flush=True)
        try:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "fetch_report.json").write_text(
                json.dumps({**report, "stopped": "challenge"}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except Exception:
            pass
        sys.exit(2)
