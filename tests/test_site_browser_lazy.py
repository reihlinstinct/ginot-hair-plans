"""Browser coverage: lazy. Shared fixtures stay in test_site_browser."""

import datetime
import functools
import json
import threading

from test_site_browser import _Quiet, _ThreadingServer, recorded_page

from ginot.dates import today_il

pytest_plugins = ["test_site_browser"]


# Section: Lazy


# --- #441: default subset first, full list lazily -------------------------

_LAZY_OBJ = "תחילת פרסום הבקשה להקלה"
_LAZY_REVIEW = "שולמה מקדמה"


def _lazy_site(tmp_path, evidence=(), dated=False):
    """Synthetic site: 3 open objection rows (in the default subset) and 30
    review-group rows (full list only), one with a unique search word."""
    from ginot.page import render_site

    source = tmp_path / "source"
    source.mkdir()
    requests = [
        {
            "tik_num": f"2026/01{i:02d}.00",
            "status": _LAZY_OBJ,
            "address": f"רחוב אלף {i}",
        }
        for i in range(3)
    ] + [
        {
            "tik_num": f"2026/02{i:02d}.00",
            "status": _LAZY_REVIEW,
            "address": "רחוב ייחודי 7" if i == 29 else f"רחוב בית {i}",
        }
        for i in range(30)
    ]
    if dated:  # open objection windows, so the urgency list is not empty
        today = today_il()
        for i, r in enumerate(requests[:3]):
            r["publication_start"] = (today - datetime.timedelta(days=5)).isoformat()
            r["publication_end_planned"] = (
                today + datetime.timedelta(days=5 + i)
            ).isoformat()
    (source / "permit_requests.json").write_text(
        json.dumps({"requests": requests}, ensure_ascii=False), encoding="utf-8"
    )
    (source / "publications_active.json").write_text(json.dumps(list(evidence)))
    out = tmp_path / "site"
    render_site([], [], str(out), permits_path=str(source / "permit_requests.json"))
    handler = functools.partial(_Quiet, directory=str(out))
    srv = _ThreadingServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


def _count_requests(pg):
    seen = {"permits.html": 0, "permits-default.html": 0}

    def on_request(req):
        name = req.url.rsplit("/", 1)[-1].split("?", 1)[0]
        if name in seen:
            seen[name] += 1

    pg.on("request", on_request)
    return seen


def test_default_load_fetches_only_the_subset(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.wait_for_timeout(300)
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            assert visible.count() == 3
            assert pg.locator("#pfload").inner_text() == ""
            assert errors == []
    finally:
        srv.shutdown()


def test_search_outside_subset_loads_full_list_once(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            # a concurrent burst of triggers shares one request
            pg.evaluate(
                "Promise.all([window.__loadFullPermits(), window.__loadFullPermits()])"
            )
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsLoaded === true")
            # the review group is not selected by default: select it
            # (the chip sits behind the "more statuses" disclosure)
            pg.evaluate(
                """document.querySelector('#pfgroups .chip[data-group="review"]').click()"""
            )
            row = pg.locator('tr[data-tik="2026/0229.00"]')
            row.wait_for(state="visible")
            pg.locator("#pfq").fill("רחוב")
            pg.locator("#pmore").click()
            assert seen == {"permits.html": 1, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_full_list_failure_shows_retry_and_keeps_subset(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            state = {"fail": True}

            def handle(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", handle)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsFailed === true")
            assert pg.locator("#pfretry").is_visible()
            # no counters computed from the subset while the view is incomplete
            assert pg.locator("#pfcount").inner_text() == ""
            assert pg.locator("#pfunknown").inner_text() == ""
            # a non-default view never shows subset results as if complete
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 0
            assert pg.locator("#permits-table tbody tr").count() == 3  # subset kept
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr").count() == 33
            # back to the default view: same 3 rows as the subset showed
            pg.locator("#pfreset").click()
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert seen["permits.html"] == 2
            assert errors == []
    finally:
        srv.shutdown()


def test_evidence_outside_subset_triggers_full_load(tmp_path, browser, request):
    # Evidence for a tik the render did not know: the subset is older than
    # the daily publication list, so the page loads the full list itself.
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsLoaded === true")
            row = pg.locator('tr[data-tik="2026/0205.00"]')
            row.wait_for(state="visible")
            assert row.get_attribute("data-group") == "pubcheck"
            assert seen == {"permits.html": 1, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_default_view_urgency_and_map_rows_match_full_load(tmp_path, browser, request):
    """The map draws the visible permit rows (plan-map.js permitRows) and the
    urgency list scans the obj rows: both must be the same on the subset as
    after the full list loads, in the default view."""
    srv, url = _lazy_site(tmp_path, dated=True)
    visible = (
        "Array.from(document.querySelectorAll('#permits-table tbody tr'))"
        ".filter(r=>!r.classList.contains('filtered-out')).map(r=>r.dataset.tik)"
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            subset_rows = pg.evaluate(visible)
            subset_urgent = pg.locator("#urgent-list").inner_text()
            subset_count = pg.locator("#pfcount").inner_text()
            assert len(subset_rows) == 3
            assert "2026/0100.00" in subset_urgent
            pg.evaluate("window.__loadFullPermits()")
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate(visible) == subset_rows
            assert pg.locator("#urgent-list").inner_text() == subset_urgent
            assert pg.locator("#pfcount").inner_text() == subset_count
            assert errors == []
    finally:
        srv.shutdown()


def test_old_evidence_outside_subset_does_not_load_full_list(
    tmp_path, browser, request
):
    """Evidence outside the overlay window (here: a closed request published
    years ago) promotes nothing, so it must not trigger the 12 MB fetch. On
    the committed data three such entries made every default load fetch it."""
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2019/0001.00",
                    "in_polygon": True,
                    "publication_date": "2019-04-17",
                    "objection_deadline": None,
                }
            ]
        )
    )
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function(
                "window.__permitsDefaultLoaded === true "
                "&& window.__permitPublicationEvidenceLoaded === true"
            )
            pg.wait_for_timeout(300)
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            assert errors == []
    finally:
        srv.shutdown()


def test_new_unmapped_subset_status_is_visible_without_full_fetch(
    tmp_path, browser, request
):
    """#622: a feed fragment can add a group absent from the weekly shell."""
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)

            def new_status(route):
                original = route.fetch().text()
                # Only the fragment changes, not index.html or its chips.
                replacement = original.replace(
                    "data-group='obj'", "data-group='unmapped'"
                )
                route.fulfill(body=replacement, content_type="text/html")

            pg.route("**/permits-default.html", new_status)
            pg.route("**/permits.html", new_status)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            chip = pg.locator('#pfgroups .chip[data-group="unmapped"]')
            assert chip.count() == 1
            assert "sel" in chip.get_attribute("class")
            assert chip.get_attribute("data-default") == "1"
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            assert visible.count() == 3
            assert seen == {"permits.html": 0, "permits-default.html": 1}
            chip.click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator('#pfgroups .chip[data-group="unmapped"]').count() == 1
            pg.locator("#pfreset").click()
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert "sel" in chip.get_attribute("class")
            assert seen["permits.html"] == 1
            assert errors == []
    finally:
        srv.shutdown()


def test_full_install_failure_can_retry_after_table_returns(tmp_path, browser, request):
    """#623: an unavailable target must not latch the shared promise forever."""
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.evaluate("""async () => {
              window.__savedPermitBody=document.querySelector('#permits-table tbody');
              window.__savedPermitBody.remove();
              window.__firstInstallResult=await window.__loadFullPermits();
              document.querySelector('#permits-table').appendChild(window.__savedPermitBody);
            }""")
            assert pg.evaluate("window.__firstInstallResult") is False
            pg.evaluate("window.__loadFullPermits()")
            pg.wait_for_function("window.__permitsLoaded === true", timeout=2000)
            assert seen["permits.html"] == 2
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert errors == []
    finally:
        srv.shutdown()


def test_subset_and_full_failure_offer_retry_in_default_view(
    tmp_path, browser, request
):
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            publications = []
            publication_state = {"release": False}

            def publication(route):
                if publication_state["release"]:
                    route.fulfill(content_type="application/json", body="[]")
                else:
                    publications.append(route)

            pg.route("**/publications_active.json", publication)
            pg.route(
                "**/permits-default.html", lambda r: r.fulfill(status=503, body="")
            )
            state = {"fail": True}

            def full(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", full)
            pg.goto(url)
            pg.wait_for_function(
                "window.__permitsDefaultFailed && window.__permitsFailed"
            )
            publication_state["release"] = True
            for route in publications:
                route.fulfill(content_type="application/json", body="[]")
            pg.wait_for_function(
                "window.__permitPublicationEvidenceLoaded && window.__permitOfficialDeadlines"
            )
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            pg.locator("#pfq").fill("ייחודי")
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            pg.locator("#pfreset").click()
            assert pg.locator("#pfretry").is_visible()
            assert pg.locator("#pfcount").inner_text() == ""
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 3
            assert errors == []
    finally:
        srv.shutdown()


def test_late_publication_overlay_refreshes_urgent_list(tmp_path, browser, request):
    srv, url = _lazy_site(tmp_path, dated=True)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pending = []
            count = {"n": 0}
            deadline = (today_il() + datetime.timedelta(days=5)).isoformat()
            evidence = [
                {
                    "tik_num": "2026/0100.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": deadline,
                }
            ]

            def publications(route):
                count["n"] += 1
                if count["n"] == 1:
                    route.fulfill(
                        content_type="application/json", body=json.dumps(evidence)
                    )
                else:
                    pending.append(route)

            def subset(route):
                text = (
                    route.fetch()
                    .text()
                    .replace("data-group='obj'", "data-group='review'")
                )
                route.fulfill(content_type="text/html", body=text)

            pg.route("**/publications_active.json", publications)
            pg.route("**/permits-default.html", subset)
            pg.goto(url, wait_until="domcontentloaded")
            pg.wait_for_function(
                "window.__permitsDefaultLoaded && window.__permitOfficialDeadlines"
            )
            assert "2026/0100.00" not in pg.locator("#urgent-list").inner_text()
            assert len(pending) == 1
            pending[0].fulfill(
                content_type="application/json", body=json.dumps(evidence)
            )
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded")
            assert "2026/0100.00" in pg.locator("#urgent-list").inner_text()
            assert (
                pg.locator('tr[data-tik="2026/0100.00"]').get_attribute("data-group")
                == "obj"
            )
            assert errors == []
    finally:
        srv.shutdown()


def test_failed_evidence_full_load_offers_retry_and_keeps_subset(
    tmp_path, browser, request
):
    """A current publication for a permit missing from the subset makes the
    page fetch the full list from the default view. If that fails, the subset
    stays visible but the page must say so and offer retry, even after a
    later apply() (CodeRabbit 4389333868)."""
    srv, url = _lazy_site(tmp_path)
    (tmp_path / "site" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0205.00",
                    "in_polygon": True,
                    "publication_date": today_il().isoformat(),
                    "objection_deadline": None,
                }
            ]
        )
    )
    state = {"fail": True}

    def full(route):
        if state["fail"]:
            route.fulfill(status=503, body="")
        else:
            route.continue_()

    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.route("**/permits.html", full)
            pg.goto(url)
            pg.wait_for_function("window.__permitsFailed === true")
            assert pg.locator("#pfretry").is_visible()
            visible = pg.locator("#permits-table tbody tr:not(.filtered-out)")
            subset_tiks = pg.locator("#permits-table tbody tr").evaluate_all(
                '(rows) => rows.map(r => r.getAttribute("data-tik"))'
            )
            assert subset_tiks
            assert visible.count() == len(subset_tiks)  # the subset stays
            pg.locator("#pfreset").click()  # a later apply() keeps the state
            assert pg.locator("#pfretry").is_visible()
            assert visible.count() == len(subset_tiks)
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.locator("#pfload").inner_text() == ""
            pg.locator('tr[data-tik="2026/0205.00"]').wait_for(state="visible")
            assert (
                pg.locator('tr[data-tik="2026/0205.00"]').get_attribute("data-group")
                == "pubcheck"
            )
            assert errors == []
    finally:
        srv.shutdown()
