#!/usr/bin/env python3
"""Mavat check mode (issue #32, option A): headless Chromium via
Playwright through the owner-operated L2TP tunnel. For each tracked
deposit-stage plan (data/mavat_tracked_plans.json) opens the public SV4
plan page and captures:

  1. the objection-deadline text ("מועד אחרון להגשת הערות...") and the
     plan's current station/status -> data/mavat_plan_status.json
  2. a normalized-text fingerprint of the page -> stored in the same
     file; future runs diff fingerprints to flag changed plan pages.
  3. an API snapshot of the plan's own public SV4 data JSON (document
     lists with editing dates, committee decisions, publication
     statuses, quantities, opposition count) -> diffed per category so
     NEW BACKGROUND DOCUMENTS and NEW COMMITTEE DECISIONS are flagged
     (page text does not expose them; gap verified 2026-10-21).

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
from zoneinfo import ZoneInfo

TRACKED = "data/mavat_tracked_plans.json"
OUT = "data/mavat_plan_status.json"
SV4 = "https://mavat.iplan.gov.il/SV4/1/{mp_id}/310"
API = "https://mavat.iplan.gov.il/rest/api/SV4/1?mid={mp_id}&guid=0"
PACE_SECONDS = 6
# Hard-challenge detection is positive-content based (issue #32): the
# legitimate SV4 page always loads a reCAPTCHA script token for its gated
# data APIs, so a raw-HTML substring match fires on every healthy page.
# Instead, a page passes when it actually shows plan content; only a page
# WITHOUT plan content is inspected for challenge markers, and only in
# its visible text (interstitials render their message; they do not
# render the plan).
CHALLENGE_PATTERNS = (
    "recaptcha",
    "captcha",
    "px-captcha",
    "perimeterx",
    "incapsula",
    "access denied",
    "request blocked",
    "are you a robot",
)
CONTENT_MARKERS = (
    "מועד אחרון להגשת הערות",
    "מטרת התכנית",
    "הפקדה להתנגדויות",
    "מסמכים",
    "גוש",
    "חלקה",
)
DEADLINE_RE = re.compile(r"מועד אחרון להגשת הערות[^<\\n]{0,120}")
STATION_RE = re.compile(
    r"(הפקדה להתנגדויות/השגות|בבדיקה תכנונית|במילוי תנאים להפקדה|הכרעה בהתנגדויות|אישור)"
)


def normalize(text):
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


PAGE_API_JSON = {}


def scrape_plan(page, mp_id, num):
    def _capture(resp):
        try:
            if "/rest/api/SV4/1" in resp.url and f"mid={mp_id}" in resp.url:
                PAGE_API_JSON[mp_id] = resp.json()
        except Exception:
            pass

    page.on("response", _capture)
    page.goto(SV4.format(mp_id=mp_id), wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    time.sleep(2)
    text = normalize(page.inner_text("body")) if page.query_selector("body") else ""
    # Positive-content check: the plan number or a plan-page marker must
    # be visible. Instrumented: the matched marker is logged so the first
    # re-run can be audited against the old behaviour.
    marker_hit = (
        num if num in text else next((m for m in CONTENT_MARKERS if m in text), "")
    )
    if not marker_hit:
        low = text.lower()
        if any(p in low for p in CHALLENGE_PATTERNS):
            raise RuntimeError("hard_challenge")
        raise RuntimeError(f"no_plan_content (page_chars={len(text)})")
    print(f"  content check: positive via {marker_hit!r} (page_chars={len(text)})")
    deadline = ""
    m = DEADLINE_RE.search(text)
    if m:
        deadline = m.group(0).strip()
    station = ""
    m = STATION_RE.search(text)
    if m:
        station = m.group(1)
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return {
        "deadline_text": deadline,
        "station_text": station,
        "fingerprint": fingerprint,
        "page_chars": len(text),
    }


API_DOC_ARRAYS = ("rsPlanDocs", "rsPlanDocsAdd", "rsPlanDocsGen", "rsPubDocs")


def _s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def api_snapshot(page, mp_id, page_url):
    """Fetch the plan's own public SV4 data JSON (the same endpoint the
    plan page itself calls) using the browser context's session, and
    reduce it to a diff-able snapshot: signed/background document list,
    committee decisions, internet-publication statuses and quantities.

    These lists are NOT fully visible in the page text, so the page-text
    fingerprint alone misses new background documents and new committee
    decisions (verified 2026-10-21)."""
    # in-page fetch: the plan page itself calls this endpoint, so the
    # page JS context (session cookies + any page-set headers) is the
    # only context that reliably gets 200 (ctx.request gets 401/403,
    # verified in run 39550270443).
    data = PAGE_API_JSON.get(mp_id)
    if not isinstance(data, dict):
        for attempt in (1, 2):
            data = page.evaluate(
                """async (url) => {
                  const r = await fetch(url, {credentials: 'include'});
                  if (r.status !== 200) return {__status: r.status};
                  return await r.json();
                }""",
                API.format(mp_id=mp_id),
            )
            if isinstance(data, dict) and not data.get("__status"):
                break
            time.sleep(4)
    if not isinstance(data, dict) or data.get("__status"):
        raise RuntimeError(f"api_status_{(data or {}).get('__status')}")

    docs = []
    for arr in API_DOC_ARRAYS:
        for d in data.get(arr) or []:
            docs.append(
                "|".join(
                    [
                        arr,
                        _s(d.get("ID")),
                        _s(d.get("DOC_NAME")),
                        _s(d.get("EDITING_DATE")),
                        _s(d.get("ED_DOC_INFO")),
                    ]
                )
            )
    decisions = []
    for d in data.get("rsDes") or []:
        decisions.append(
            "|".join(
                [
                    _s(d.get("MEETING_NO")),
                    _s(d.get("MEETING_DATE")),
                    _s(d.get("COMMITTE_NAME")),
                    _s(d.get("CM_NAME")),
                    _s(d.get("FO_NAME")),
                ]
            )
        )
    internet = []
    for d in data.get("rsInternet") or []:
        details = re.sub(r"<[^>]+>", " ", _s(d.get("DETAILS")))
        details = re.sub(r"\s+", " ", details)
        internet.append(
            "|".join([_s(d.get("LIS_DESC")), _s(d.get("EIS_DATE")), details])
        )
    quantities = []
    for d in data.get("rsQuantities") or []:
        quantities.append("|".join(f"{k}={_s(v)}" for k, v in sorted(d.items())))
    oppositions = data.get("rsOppositions") or []

    snap = {
        "docs": sorted(docs),
        "decisions": sorted(decisions),
        "internet": sorted(internet),
        "quantities": sorted(quantities),
        "oppositions_count": len(oppositions),
    }
    snap["fingerprint"] = hashlib.sha256(
        json.dumps(snap, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return snap


def diff_snapshots(old, new):
    """Human-readable change reasons between two api snapshots."""
    reasons = []
    if not old:
        return reasons
    for key, label in (
        ("docs", "מסמכים"),
        ("decisions", "דיונים/החלטות"),
        ("internet", "סטטוסי פרסום"),
        ("quantities", "כמויות"),
    ):
        added = [x for x in new.get(key, []) if x not in set(old.get(key, []))]
        removed = [x for x in old.get(key, []) if x not in set(new.get(key, []))]
        if added or removed:
            reasons.append(f"{label}: +{len(added)}/-{len(removed)}")
    if new.get("oppositions_count") != old.get("oppositions_count"):
        reasons.append(
            f"התנגדויות: {old.get('oppositions_count')} -> "
            f"{new.get('oppositions_count')}"
        )
    return reasons


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
            locale="he-IL",
        )
        page = ctx.new_page()
        for i, p in enumerate(plans):
            if i:
                time.sleep(PACE_SECONDS)
            num, mp_id = p["plan_number"], p["mp_id"]
            info = None
            last_msg = ""
            for attempt in range(3):
                try:
                    info = scrape_plan(page, mp_id, num)
                    break
                except RuntimeError as exc:
                    msg = str(exc)
                    if "hard_challenge" in msg:
                        print(f"{num}: {msg} - stopping (no workaround)")
                        browser.close()
                        return 2
                    if "no_plan_content" in msg:
                        last_msg = msg
                        # A single plan returning an empty shell after many
                        # successful loads is per-plan flakiness, not a block.
                        # Retry with a fresh page; only stop if it persists
                        # across plans (handled by the consecutive counter).
                        if attempt < 2:
                            print(
                                f"{num}: {msg} - retry {attempt + 1}/2 with fresh page"
                            )
                            try:
                                page.close()
                            except Exception:
                                pass
                            page = ctx.new_page()
                            time.sleep(5)
                            continue
                    raise
                except Exception as exc:
                    failures += 1
                    print(f"{num}: failed ({exc}); {failures} consecutive")
                    if failures >= 4:
                        print("aborting: repeated failures")
                        browser.close()
                        return 1
                    break
            if info is None:
                if last_msg:
                    failures += 1
                    print(
                        f"{num}: persistent no_plan_content after retries; "
                        f"recording error and continuing ({failures} consecutive)"
                    )
                    prev = old.get(num, {})
                    entry = {"mp_id": mp_id, "error": last_msg}
                    if prev.get("fingerprint"):
                        entry["fingerprint"] = prev["fingerprint"]
                        entry["station_text"] = prev.get("station_text", "")
                        entry["deadline_text"] = prev.get("deadline_text", "")
                    result[num] = entry
                    if failures >= 4:
                        print("aborting: repeated failures")
                        browser.close()
                        return 1
                continue
            failures = 0
            prev = old.get(num, {})
            try:
                api = api_snapshot(page, mp_id, SV4.format(mp_id=mp_id))
                info["api"] = api
            except Exception as exc:
                print(
                    f"{num}: api snapshot failed ({type(exc).__name__}: {exc}) - "
                    f"page fingerprint only this run"
                )
                api = None
            reasons = []
            if prev.get("fingerprint") and prev["fingerprint"] != info["fingerprint"]:
                reasons.append("טקסט העמוד השתנה")
            if api and prev.get("api"):
                reasons += diff_snapshots(prev["api"], api)
            if reasons:
                changed.append({"plan": num, "reasons": reasons})
            info["mp_id"] = mp_id
            result[num] = info
            print(
                f"{num}: station={info['station_text'] or '?'} "
                f"deadline={'yes' if info['deadline_text'] else 'no'} "
                f"fp={info['fingerprint']} "
                f"api_fp={api['fingerprint'] if api else '-'} "
                f"changed={'; '.join(reasons) if reasons else 'no'}"
            )
        browser.close()

    payload = {
        "generated": datetime.datetime.now(ZoneInfo("Asia/Jerusalem")).date().isoformat(),  # issue #331: IL not runner UTC
        "source": "Mavat SV4 plan pages via headless Chromium through the owner VPN",
        "changed_since_previous": changed,
        "plans": result,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT}: {len(result)} plans, {len(changed)} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
