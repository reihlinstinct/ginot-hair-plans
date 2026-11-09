"""Browser coverage: the email signup entry point (issue #941 follow-up).

Shared fixtures stay in test_site_browser. The endpoint is stubbed with a
route, so no mail is sent and no network is used.
"""

import pytest
from test_site_browser import TODAY  # noqa: F401  (fixtures need the module)

pytest_plugins = ["test_site_browser"]

ENDPOINT = "https://ginot-hair-plans.vercel.app/api/send_plan_email"


# Section: Signup button on the main page
def test_language_select_typeahead_and_escape_do_not_navigate(page, served):
    page.goto(served + "/email.html")
    page.focus("#lang-select")
    page.keyboard.press("e")  # type-ahead picks EN; must not navigate
    page.wait_for_timeout(300)
    assert page.url.endswith("/email.html")
    page.keyboard.press("Escape")  # cancels the pending choice
    assert page.locator("#lang-select").input_value() == "email.html"
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    page.keyboard.press("Tab")
    page.wait_for_timeout(300)
    assert page.url.endswith("/email.html")


def test_language_select_back_restores_the_current_language(page, served):
    page.goto(served + "/email.html")
    page.select_option("#lang-select", label="EN")
    page.wait_for_url("**/en/email.html")
    page.go_back()
    page.wait_for_url("**/email.html")
    page.wait_for_timeout(300)
    assert page.locator("#lang-select").input_value() == "email.html"


@pytest.mark.evidence
def test_signup_button_visible_and_links_to_form_on_phone(mobile_page):
    """A visible, tappable button leads from the main page to the email form."""
    cta = mobile_page.locator("a.cta-email")
    assert cta.count() == 1
    box = cta.bounding_box()
    assert box and box["height"] >= 36 and box["width"] > 100, box
    assert box["x"] >= 0 and box["x"] + box["width"] <= 391, box
    cta.tap()
    mobile_page.wait_for_url("**/email.html")
    assert mobile_page.locator("#email-form").is_visible()


def test_signup_button_visible_on_desktop(page):
    assert page.locator("a.cta-email").is_visible()
    assert page.locator("a.cta-email").get_attribute("href") == "email.html"


# Section: The form itself
@pytest.mark.evidence
def test_signup_form_posts_expected_payload_and_confirms(mobile_page, served):
    sent = []

    def handle(route, request):
        if request.method == "OPTIONS":
            route.fulfill(
                status=204,
                headers={
                    "access-control-allow-origin": "*",
                    "access-control-allow-headers": "Content-Type",
                },
            )
            return
        sent.append(request.post_data_json)
        route.fulfill(
            status=200,
            headers={"access-control-allow-origin": "*"},
            content_type="application/json",
            body='{"ok": true}',
        )

    mobile_page.route(ENDPOINT, handle)
    mobile_page.goto(served + "/email.html")
    options = mobile_page.locator("#plan option")
    assert options.count() >= 1
    plan = options.first.get_attribute("value")
    mobile_page.select_option("#plan", plan)
    mobile_page.fill("#email", "reader@example.com")
    mobile_page.check("#subscribe")
    mobile_page.tap("#email-form button[type=submit]")
    mobile_page.wait_for_function(
        "document.getElementById('form-status').textContent.includes('אישור')"
    )
    assert len(sent) == 1, sent
    assert sent[0]["email"] == "reader@example.com"
    assert sent[0]["plan_number"] == plan
    assert sent[0]["subscribe"] is True
    assert sent[0]["lang"] == "he"
    assert sent[0]["website"] == ""  # honeypot stays empty


def test_signup_form_preselects_plan_from_query(page, served):
    page.goto(served + "/email.html")
    values = page.locator("#plan option").evaluate_all("els => els.map(e => e.value)")
    assert len(values) >= 2, values
    target = values[-1]
    page.goto(served + "/email.html?plan=" + target)
    assert page.locator("#plan").input_value() == target
    page.goto(served + "/email.html?plan=does-not-exist")
    assert page.locator("#plan").input_value() == values[0]


def test_signup_form_shows_error_when_endpoint_fails(page, served):
    page.route(ENDPOINT, lambda route, req: route.abort())
    page.goto(served + "/email.html")
    page.fill("#email", "reader@example.com")
    page.click("#email-form button[type=submit]")
    page.wait_for_function(
        "document.getElementById('form-status').textContent.includes('נסו')"
    )


@pytest.mark.evidence
def test_signup_form_fits_a_phone_without_sideways_scroll(mobile_page, served):
    mobile_page.goto(served + "/email.html")
    assert mobile_page.evaluate("document.documentElement.scrollWidth") <= 391
    for sel in ("#plan", "#email", "#email-form button[type=submit]"):
        box = mobile_page.locator(sel).bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 391, (sel, box)


# Section: Language selector (a select; options come from i18n/strings.json)
def _doc():
    import json
    from pathlib import Path

    return json.loads(
        (Path(__file__).parent.parent / "src/ginot/i18n/strings.json").read_text(
            encoding="utf-8"
        )
    )


def test_language_select_lists_document_languages_and_navigates(page, served):
    doc = _doc()
    page.goto(served + "/email.html")
    opts = page.locator("#lang-select option")
    assert opts.count() == len(doc["languages"])
    assert (
        page.locator("nav.lang-switch a").count() == 0
        or not page.locator("nav.lang-switch a").first.is_visible()
    )  # links are the no-JS fallback only
    for code, m in doc["languages"].items():
        page.goto(served + "/email.html")
        page.select_option("#lang-select", label=m["label"])
        page.wait_for_load_state()
        page.wait_for_selector("#lang-select")
        assert page.locator("html").get_attribute("dir") == m["dir"]
        assert page.locator("html").get_attribute("lang") == m["lang"]
        assert page.locator("#lang").get_attribute("value") == code
        selected = page.locator("#lang-select option:checked").text_content()
        assert selected == m["label"]
        title = page.locator("#lang-select option:checked").get_attribute("title")
        assert title == m["name"]
        assert page.locator("label[for=lang-select]").is_visible()


def test_language_select_keyboard_does_not_navigate_on_arrows(page, served):
    page.goto(served + "/email.html")
    page.focus("#lang-select")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    assert page.url.endswith("/email.html")  # still on the Hebrew page
    target = page.locator("#lang-select").input_value()
    assert target and target != "email.html"
    page.keyboard.press("Enter")
    page.wait_for_url("**/" + target)
    assert page.locator("html").get_attribute("lang") != "he"


@pytest.mark.evidence
def test_language_select_fits_a_phone_in_rtl_and_ltr(mobile_page, served):
    for path in ("/email.html", "/ar/email.html", "/en/email.html"):
        mobile_page.goto(served + path)
        box = mobile_page.locator("#lang-select").bounding_box()
        assert box and box["height"] >= 36, box
        assert box["x"] >= 0 and box["x"] + box["width"] <= 391, (path, box)
        assert mobile_page.evaluate("document.documentElement.scrollWidth") <= 391
