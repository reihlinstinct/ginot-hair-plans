#!/usr/bin/env python3
"""Capture the public ykpubdata permit viewer's own XHR calls, through the
owner-operated L2TP tunnel, using headless Chromium.

Why: the viewer (ykpubdata.jerusalem.muni.il) is a React SPA that talks to
jerbasicserviceapi via a generic gateway (Db/ExecuteSelect with
{Cnn, ProcName, Parameters}). The real ProcName ids and parameter shapes are
only observable in the viewer's own traffic. This script loads PUBLIC pages
(no login) and records the requests the viewer itself makes, so the permit
feed can mirror one of them exactly, politely.

Anti-bot rule (owner's standing instruction): no bypass of a real
challenge/CAPTCHA. If a hard challenge, throttling or block appears, stop
and report (exit 2) instead of working around it.

Logged/artifact data: request URLs + POST payloads of the viewer's own
gateway calls (public query parameters such as gush/helka) and response
sizes/keys only. No response bodies with personal data are stored.

Exit codes: 0 = captured >=1 gateway call; 2 = anti-bot challenge/block;
1 = anything else (nothing captured, error).
"""
import json, sys, time

from playwright.sync_api import sync_playwright

VIEWER = "https://ykpubdata.jerusalem.muni.il"
# Public details page for the known permit request on gush 30025 helka 126
# (Alfasi 9, TAMA 38 s.13) - already public in the viewer.
DETAILS = (VIEWER + "/Rishui/BakashalInfo"
           "?TikNum=1993/0664.03&SystemCode=26400046")
API_MARK = "jerbasicserviceapi.jerusalem.muni.il"
CHALLENGE_MARKERS = ("incapsula", "recaptcha", "captcha", "_challenge",
                     "px-captcha", "perimeterx", "request blocked",
                     "access denied")

captured = []
challenge = {"hit": False}


def on_request(req):
    if API_MARK in req.url:
        captured.append({"method": req.method, "url": req.url,
                         "post_data": req.post_data})


def on_response(resp):
    if challenge["hit"]:
        return
    try:
        ct = (resp.headers.get("content-type") or "").lower()
        if "html" in ct and resp.status in (403, 429, 503):
            body = resp.body()[:200000].lower()
            if any(m.encode() in body for m in CHALLENGE_MARKERS):
                challenge["hit"] = True
    except Exception:
        pass


def check_page_for_challenge(page):
    try:
        txt = page.content()[:200000].lower()
    except Exception:
        return
    if any(m in txt for m in CHALLENGE_MARKERS):
        challenge["hit"] = True


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        page = ctx.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        # 1. Public search page: capture the viewer's search-shaped call.
        page.goto(VIEWER + "/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        check_page_for_challenge(page)
        shot1 = "/tmp/yk_search.png"
        page.screenshot(path=shot1, full_page=False)

        if not challenge["hit"]:
            # Try to drive the public search form: gush 30025, helka 126.
            try:
                gush = page.get_by_label("גוש", exact=False).first
                gush.fill("30025", timeout=5000)
                helka = page.get_by_label("חלקה", exact=False).first
                helka.fill("126", timeout=5000)
                btn = page.get_by_role("button", name="חיפוש").first
                btn.click(timeout=5000)
                page.wait_for_timeout(6000)
            except Exception as e:
                print(json.dumps({"event": "search_form_not_driven",
                                  "error_kind": type(e).__name__}))
            check_page_for_challenge(page)

        # 2. Public details page: capture detail-shaped calls.
        if not challenge["hit"]:
            page.goto(DETAILS, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            check_page_for_challenge(page)
            page.screenshot(path="/tmp/yk_details.png", full_page=False)

        browser.close()

    with open("/tmp/yk_capture.json", "w") as f:
        json.dump(captured, f, ensure_ascii=False, indent=1)

    if challenge["hit"]:
        print(json.dumps({"result": "anti_bot_challenge",
                          "captured": len(captured)}))
        return 2
    for c in captured:
        print(json.dumps({"captured": c["method"] + " " + c["url"],
                          "post_data": c["post_data"]}, ensure_ascii=False))
    print(json.dumps({"result": "captured" if captured else "nothing_captured",
                      "gateway_calls": len(captured)}))
    return 0 if captured else 1


if __name__ == "__main__":
    sys.exit(main())
