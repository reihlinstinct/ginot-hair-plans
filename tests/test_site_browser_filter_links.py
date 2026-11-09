"""Browser coverage: filter links. Shared fixtures stay in test_site_browser."""

from test_site_browser import _d, plan_ids

pytest_plugins = ["test_site_browser"]


# Section: Filter links


def test_filter_link_hebrew_and_permit_state_roundtrip(page):
    page.fill("#fq", "תכנית")
    page.check("#fappr")
    page.click('#plans th button[data-sort="num"]')
    page.fill("#pfq", "הפלמח")
    page.wait_for_function("window.__permitsLoaded === true")
    expected_plans = plan_ids(page)
    expected_permits = page.locator(
        "#permits-table tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    link = page.evaluate("window.GinotFilterLinks.build()")
    assert "filters=1" in link
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#fq") == "תכנית"
    assert page.is_checked("#fappr")
    assert page.input_value("#pfq") == "הפלמח"
    assert plan_ids(page) == expected_plans
    assert (
        page.locator(
            "#permits-table tr:not(.filtered-out) td:first-child"
        ).all_inner_texts()
        == expected_permits
    )


def test_filter_link_invalid_values_and_clipboard_fallback(page):
    url = page.url.split("?")[0]
    page.goto(
        url + "?filters=1&plan.fflag=garbage&plan.ffrom=2026-02-30&plan.fappr=no#plans"
    )
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fflag") == ""
    assert page.input_value("#ffrom") == ""
    assert not page.is_checked("#fappr")
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('denied'))},configurable:true})"
    )
    page.click("#copy-plan-link")
    link = page.locator('input[aria-label="קישור לסינון הנוכחי"]:visible')
    assert link.count() == 1
    assert "#plans" in link.input_value()
    assert page.locator('[role="status"]', has_text="לא הועתק").count() == 1


def test_filter_link_copy_success_and_unknown_version(page):
    page.goto(page.url.split("?")[0] + "?filters=99&plan.fq=ignored&today=2026-10-26")
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fq") == ""
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{value:{writeText:t=>{window.__copied=t;return Promise.resolve();}},configurable:true})"
    )
    page.click("#copy-plan-link")
    page.wait_for_function("window.__copied")
    assert "today=2026-10-26" in page.evaluate("window.__copied")
    assert page.locator('[role="status"]', has_text="הקישור הועתק").count() == 1


def test_filter_link_expanded_groups_and_dates(page):
    page.click("#more")
    page.check("#fappr")
    page.click("#more")
    page.check("#pfclosed")
    page.wait_for_function("window.__permitsLoaded")
    page.uncheck("#pfopenonly")
    page.fill("#pffrom", _d(-120))
    expected_groups = page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.getAttribute('data-group')).sort()"
    )
    link = page.evaluate("GinotFilterLinks.build()")
    expected_ids = plan_ids(page)
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#pffrom") == _d(-120)
    assert page.is_checked("#pfclosed")
    assert not page.is_checked("#pfopenonly")
    assert (
        page.locator("#pfgroups .chip.sel").evaluate_all(
            "els=>els.map(e=>e.getAttribute('data-group')).sort()"
        )
        == expected_groups
    )
    assert plan_ids(page) == expected_ids


def test_filter_link_closed_only_selects_terminal_groups(page):
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfclosed=1")
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        assert page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.classList.contains('sel')"
        )
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfclosed=1&permit.groups=obj")
    page.wait_for_function("window.__permitsLoaded")
    assert page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.getAttribute('data-group'))"
    ) == ["obj"]


def test_filter_link_unknown_keys_do_not_load_and_are_preserved(page):
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.unknown=x&plan.note=hello")
    page.wait_for_function("window.__permitsDefaultLoaded")
    assert not any("/permits.html" in url for url in requests)
    link = page.evaluate("GinotFilterLinks.build()")
    assert "permit.unknown=x" in link and "plan.note=hello" in link


def test_filter_link_copy_disabled_while_url_state_pending(page):
    held = []
    page.route("**/permits.html", lambda route: held.append(route))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfq=הפלמח")
    page.wait_for_function("document.getElementById('pfload').textContent.length > 0")
    assert page.is_disabled("#copy-plan-link") and page.is_disabled("#copy-permit-link")
    for _ in range(250):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "full permit request did not arrive within 5 seconds"
    held[0].continue_()
    page.wait_for_function("window.__permitsLoaded")
    assert page.is_enabled("#copy-plan-link") and page.is_enabled("#copy-permit-link")
    assert page.input_value("#pfq") == "הפלמח"


def test_filter_link_closed_with_terminal_chips_off_roundtrips(page):
    page.check("#pfclosed")
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.click()"
        )
    expected = page.locator("#pfgroups .chip.sel").evaluate_all(
        "els=>els.map(e=>e.dataset.group).sort()"
    )
    link = page.evaluate("GinotFilterLinks.build()")
    page.goto(link)
    page.wait_for_function("window.__permitsLoaded")
    assert page.is_checked("#pfclosed")
    assert (
        page.locator("#pfgroups .chip.sel").evaluate_all(
            "els=>els.map(e=>e.dataset.group).sort()"
        )
        == expected
    )


def test_filter_link_invalid_groups_uses_checkbox_fallback(page):
    page.goto(
        page.url.split("?")[0] + "?filters=1&permit.pfclosed=1&permit.groups=invalid"
    )
    page.wait_for_function("window.__permitsLoaded")
    for group in ["closed", "issued"]:
        assert page.locator('#pfgroups .chip[data-group="' + group + '"]').evaluate(
            "e=>e.classList.contains('sel')"
        )


def test_manual_permit_edit_cancels_pending_shared_url_state(page):
    held = []
    page.route("**/permits.html", lambda route: held.append(route))
    page.goto(page.url.split("?")[0] + "?filters=1&permit.pfq=הפלמח")
    page.fill("#pfq", "הרצל")
    for _ in range(250):
        if held:
            break
        page.wait_for_timeout(20)
    assert held, "full permit request did not arrive within 5 seconds"
    held[0].continue_()
    page.wait_for_function("window.__permitsLoaded")
    assert page.input_value("#pfq") == "הרצל"
    assert page.is_enabled("#copy-plan-link")


def test_restored_plan_status_syncs_legend_and_reset(page):
    status = page.locator(".plan-legend .chip").first.get_attribute("data-status")
    from urllib.parse import urlencode

    page.goto(
        page.url.split("?")[0]
        + "?"
        + urlencode({"filters": "1", "plan.fstatus": status})
    )
    page.wait_for_function("window.__rowsLoaded")
    assert page.input_value("#fstatus") == status
    assert page.locator(".plan-legend .chip.sel").evaluate_all(
        "els=>els.map(e=>e.dataset.status)"
    ) == [status]
    page.click("#freset")
    assert page.locator(".plan-legend .chip.sel").count() == 0


def test_implicit_or_queries_roundtrip_without_new_controls(page):
    page.fill("#fq", "200-1 | 300-1")
    expected_plans = plan_ids(page)
    assert "200-1" in expected_plans and "300-1" in expected_plans
    page.fill("#pfq", "פלמח 41 | אלפסי 9")
    page.wait_for_function("window.__permitsLoaded === true")
    page.fill("#pffrom", "")
    page.uncheck("#pfopenonly")
    expected = page.locator(
        "#permits-table tr:not(.filtered-out) td:first-child"
    ).all_inner_texts()
    assert "2026/0439.00" in expected and "2020/0001.01" in expected
    assert page.locator("#fq").count() == page.locator("#pfq").count() == 1
    link = page.evaluate("window.GinotFilterLinks.build()")
    assert "%7C" in link
    page.goto(link)
    page.wait_for_function("window.__rowsLoaded && window.__permitsLoaded")
    assert page.input_value("#fq") == "200-1 | 300-1"
    assert page.input_value("#pfq") == "פלמח 41 | אלפסי 9"
    assert plan_ids(page) == expected_plans
    assert (
        page.locator(
            "#permits-table tr:not(.filtered-out) td:first-child"
        ).all_inner_texts()
        == expected
    )
