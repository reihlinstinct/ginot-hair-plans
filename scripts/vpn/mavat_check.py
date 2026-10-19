#!/usr/bin/env python3
"""Mavat check mode (issue #32, option A): headless Chromium via
Playwright through the owner-operated L2TP tunnel. For each tracked
deposit-stage plan (data/mavat_tracked_plans.json) opens the public SV4
plan page and captures:

  1. the objection-deadline text ("מועד אחרון להגשת הערות...") and the
     plan's current station/status -> data/mavat_plan_status.json
  2. a normalized-text fingerprint of the page -> stored in the same
     file; future runs diff fingerprints to flag changed plan pages.

Public pages only, no login, slow pacing, and on any hard challenge /
CAPTCHA / throttling the run stops with exit 2 (no workaround).

Requires: playwright (pip) + chromium (playwright install chromium).
"""
import datetime
import hashlib
import json
import re
import sys
import time

TRACKED = "data/mavat_tracked_plans.json"
OUT = "data/mavat_plan_status.json"
SV4 = "https://mavat.iplan.gov.il/SV4/1/{mp_id}/310"
PACE_SECONDS = 6
CHALLENGE_PATTERNS = (
    "recaptcha", "captcha", "px-captcha", "perimeterx", "incapsula",
    "access denied", "request blocked", "are you a robot",
)
DEADLINE_RE = re.compile(r"מועד אחרון להגשת הערות[^<\\n]{0,120}")
STATION_RE = re.compile(r"(הפקדה להתנגדויות/השגות|בבדיקה תכנונית|במילוי תנאים להפקדה|הכרעה בהתנגדויות|אישור)")


def normalize(text):
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def scrape_plan(page, mp_id):
    page.goto(SV4.format(mp_id=mp_id), wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    time.sleep(2)
    html = page.content()
    low = html.lower()
    if any(p in low for p in CHALLENGE_PATTERNS):
        raise RuntimeError("hard_challenge")
    text = normalize(page.inner_text("body")) if page.query_selector("body") else ""
    deadline = ""
    m = DEADLINE_RE.search(text)
    if m:
        deadline = m.group(0).strip()
    station = ""
    m = STATION_RE.search(text)
    if m:
        station = m.group(1)
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {"deadline_text": deadline, "station_text": station,
            "fingerprint": fingerprint, "page_chars": len(text)}


def main():
    from playwright.sync_api import sync_playwright

    with open(TRACKED, encoding="utf-8") as fh:
        plans = json.load(fh)["plans"]
    try:
        with open(OUT, encoding="utf-8") as fh:
            old = json.load(fh).get("plans", {})
    except (FileNotFoundError, json.JSONDecodeError):
        old = {}

    result, changed, failures = {}, [], 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="he-IL")
        page = ctx.new_page()
        for i, p in enumerate(plans):
            if i:
                time.sleep(PACE_SECONDS)
            num, mp_id = p["plan_number"], p["mp_id"]
            try:
                info = scrape_plan(page, mp_id)
            except RuntimeError as exc:
                if "hard_challenge" in str(exc):
                    print(f"{num}: hard challenge - stopping (no workaround)")
                    browser.close()
                    return 2
                raise
            except Exception as exc:
                failures += 1
                print(f"{num}: failed ({exc}); {failures} consecutive")
                if failures >= 4:
                    print("aborting: repeated failures")
                    browser.close()
                    return 1
                continue
            failures = 0
            prev = old.get(num, {})
            if prev.get("fingerprint") and prev["fingerprint"] != info["fingerprint"]:
                changed.append(num)
            info["mp_id"] = mp_id
            result[num] = info
            print(f"{num}: station={info['station_text'] or '?'} "
                  f"deadline={'yes' if info['deadline_text'] else 'no'} "
                  f"fp={info['fingerprint']}")
        browser.close()

    payload = {"generated": datetime.date.today().isoformat(),
               "source": "Mavat SV4 plan pages via headless Chromium through the owner VPN",
               "changed_since_previous": changed,
               "plans": result}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}: {len(result)} plans, {len(changed)} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
