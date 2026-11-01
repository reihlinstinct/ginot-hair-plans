#!/usr/bin/env python3
"""Probe public Jerusalem-municipality pages through the owner-operated
L2TP/IPsec tunnel (sandbox/direct access is 403-blocked). Read-only GET
of public pages only; any hard challenge (captcha/login wall) stops the
run red. Extracts links so the real system behind a service page can be
found. Uploads results as files for the run artifact."""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

OUT = Path("/tmp/muni_probe")
OUT.mkdir(parents=True, exist_ok=True)

CHALLENGE_MARKERS = [
    "recaptcha",
    "captcha",
    "are you a robot",
    "cloudflare",
    "אימות אנושי",
    "human verification",
]

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def main():
    urls = [u.strip() for u in os.environ.get("PROBE_URLS", "").split(",") if u.strip()]
    if not urls:
        print("no PROBE_URLS given", flush=True)
        return 1
    report = {"results": []}
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "he-IL,he;q=0.9"})
    for i, url in enumerate(urls):
        entry = {"url": url}
        try:
            r = sess.get(url, timeout=60, allow_redirects=True)
            entry["status"] = r.status_code
            entry["final_url"] = r.url
            entry["ctype"] = r.headers.get("content-type", "")
            text = r.text or ""
            low = text.lower()
            if any(m in low for m in CHALLENGE_MARKERS):
                entry["challenge"] = True
                report["results"].append(entry)
                print(f"CHALLENGE at {url} - stopping", flush=True)
                break
            fn = OUT / f"page_{i:02d}.html"
            fn.write_text(text, encoding="utf-8", errors="replace")
            entry["file"] = fn.name
            entry["bytes"] = len(text)
            links = sorted(set(re.findall(r'href="([^"]+)"', text)))
            links = [
                l
                for l in links
                if not re.search(r"\.(css|js|png|jpg|svg|ico)(\?|$)", l)
            ]
            entry["links"] = links[:120]
            # visible text excerpt (tags stripped) for quick reading
            body = re.sub(r"(?s)<(script|style).*?</\1>", " ", text)
            body = re.sub(r"(?s)<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()
            entry["text_excerpt"] = body[:3000]
        except Exception as exc:
            entry["error"] = type(exc).__name__
        report["results"].append(entry)
        print(
            f"{url} -> {entry.get('status')} ({entry.get('bytes', '?')}b)", flush=True
        )
        time.sleep(2)
    (OUT / "probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
