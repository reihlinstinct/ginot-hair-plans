#!/usr/bin/env python3
"""Browser-based probe of public Jerusalem-municipality web apps through
the owner-operated L2TP/IPsec tunnel (the apps are JS SPAs, so a plain
GET returns only the shell). Public pages only: render, read visible
text/fields/links, screenshot. Never submits forms, never logs in; any
hard challenge (captcha / login wall) stops the run red."""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("/tmp/muni_browser_probe")
OUT.mkdir(parents=True, exist_ok=True)

CHALLENGE_MARKERS = [
    "recaptcha",
    "px-captcha",
    "are you a robot",
    "אימות אנושי",
    "human verification",
]


def main():
    urls = [u.strip() for u in os.environ.get("PROBE_URLS", "").split(",") if u.strip()]
    if not urls:
        print("no PROBE_URLS given", flush=True)
        return 1
    report = {"results": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="he-IL",
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.new_page()
        for i, url in enumerate(urls):
            entry = {"url": url}
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                time.sleep(3)
                text = page.inner_text("body") if page.query_selector("body") else ""
                low = text.lower()
                if any(m in low for m in CHALLENGE_MARKERS):
                    entry["challenge"] = True
                    report["results"].append(entry)
                    print(f"CHALLENGE at {url} - stopping", flush=True)
                    break
                entry["text"] = " ".join(text.split())[:4000]
                entry["inputs"] = page.evaluate("""() =>
                  [...document.querySelectorAll('input,select,textarea,button')]
                    .map(e => ({tag: e.tagName, type: e.type || '', name: e.name || '',
                                placeholder: e.placeholder || '',
                                label: (e.innerText || e.value || '').trim().slice(0, 60)}))
                    .slice(0, 60)""")
                entry["links"] = page.evaluate("""() =>
                  [...document.querySelectorAll('a[href]')]
                    .map(a => ({href: a.href.slice(0, 200),
                                text: (a.innerText || '').trim().slice(0, 60)}))
                    .filter(l => l.text).slice(0, 80)""")
                shot = OUT / f"page_{i:02d}.png"
                page.screenshot(path=str(shot), full_page=True)
                entry["screenshot"] = shot.name
                entry["final_url"] = page.url
                print(f"{url} -> ok ({len(text)} chars)", flush=True)
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
                print(f"{url} -> {entry['error']}", flush=True)
            report["results"].append(entry)
            time.sleep(2)
        browser.close()
    with open(OUT / "probe_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
