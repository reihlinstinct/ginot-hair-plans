"""Browser coverage: recovery. Shared fixtures stay in test_site_browser."""

import json

from test_site_browser import recorded_page
from test_site_browser_lazy import _count_requests, _lazy_site

from ginot.dates import today_il

pytest_plugins = ["test_site_browser"]


# Section: Recovery


def test_full_list_render_failure_is_not_a_load_failure(tmp_path, browser, request):
    # #624: the full list fetches and installs fine, but a post-install step
    # throws. The honest state is "loaded, processing failed" with a retry
    # that re-runs the post-install steps only - not a refetch, not the
    # load-failure message.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            pg.evaluate(
                "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
            )
            pg.locator("#pfq").fill("ייחודי")
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            # not mislabeled as a load failure
            assert pg.evaluate("window.__permitsFailed") is False
            assert pg.locator("#pfretry").count() == 0
            assert pg.locator("#pfrenderretry").is_visible()
            assert "נטענה" in pg.locator("#pfload").inner_text()
            # the full list is installed: all 33 rows are in the table
            assert pg.locator("#permits-table tbody tr").count() == 33
            # ...but never unfiltered under the active query: the filter was
            # replayed, so some rows carry filtered-out (0 when it was not).
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            # retry re-runs the post-install steps without refetching
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert seen["permits.html"] == 1
            assert errors == []
    finally:
        srv.shutdown()


def test_subset_render_failure_keeps_subset_without_full_reload(
    tmp_path, browser, request
):
    # #624: a post-install failure on the subset path must keep the subset
    # rows, say what failed, and not fall into the fetch-failure catch that
    # would trigger a misleading full reload.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            seen = _count_requests(pg)

            def handle(route):
                resp = route.fetch()
                pg.evaluate(
                    "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
                )
                route.fulfill(response=resp)

            pg.route("**/permits-default.html", handle)
            pg.goto(url)
            pg.wait_for_function("window.__permitsDefaultLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            # not treated as a subset fetch failure: no fallback full reload
            assert pg.evaluate("window.__permitsDefaultFailed") is not True
            assert seen.get("permits.html", 0) == 0
            assert pg.locator("#pfrenderretry").is_visible()
            assert "נטענה" in pg.locator("#pfload").inner_text()
            assert pg.locator("#permits-table tbody tr").count() == 3
            # a later apply cycle must not wipe the render retry in default view
            pg.locator("#pfreset").click()
            assert pg.locator("#pfrenderretry").is_visible()
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert seen.get("permits.html", 0) == 0
            assert errors == []
    finally:
        srv.shutdown()


def test_evidence_loaded_fires_despite_render_failure(tmp_path, browser, request):
    # #751 CodeRabbit: a render exception in the publications callback must not
    # swallow publication-evidence-loaded - the #441 safety net would never
    # notice a newly published permit outside the subset.
    srv, url = _lazy_site(tmp_path)
    # The subset renders before the evidence exists (daily list refreshes
    # independently), so the tik is genuinely outside the subset.
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
        with recorded_page(browser, request) as (pg, _errors):
            seen = _count_requests(pg)
            patch = "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"

            def handle(route):
                resp = route.fetch()
                pg.evaluate(patch)
                route.fulfill(response=resp)

            def handle_pubs(route):
                # publications_active.json may resolve before the subset fetch:
                # install the throwing hook here too, or the publications
                # callback would render fine and the test would pass without
                # exercising the failure path it exists to pin.
                pg.evaluate(patch)
                route.continue_()

            pg.route("**/permits-default.html", handle)
            pg.route("**/publications_active.json", handle_pubs)
            pg.goto(url)
            # the safety net still triggers the full load
            pg.wait_for_function("window.__permitsLoaded === true")
            assert pg.evaluate("window.__permitsRenderFailed") is True
            assert pg.evaluate("window.__permitPublicationEvidenceLoaded") is True
            assert seen["permits.html"] == 1
    finally:
        srv.shutdown()


def test_render_failure_then_full_load_failure_shows_load_retry(
    tmp_path, browser, request
):
    # #751 CodeRabbit: subset render failure + evidence-driven full fetch that
    # also fails must surface the full-load retry (the missing permits cannot
    # be fetched through the render retry).
    srv, url = _lazy_site(tmp_path)
    # The subset renders before the evidence exists (daily list refreshes
    # independently), so the tik is genuinely outside the subset.
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
            state = {"fail": True}

            def fail_full(route):
                if state["fail"]:
                    route.fulfill(status=503, body="")
                else:
                    route.continue_()

            pg.route("**/permits.html", fail_full)

            def patch_render(route):
                resp = route.fetch()
                pg.evaluate(
                    "(window.__renderUrgent = function(){ throw new Error('synthetic') }, undefined)"
                )
                route.fulfill(response=resp)

            pg.route("**/permits-default.html", patch_render)
            pg.goto(url)
            pg.wait_for_function("window.__permitsFailed === true")
            # the full-load retry is visible, not only the render retry
            assert pg.locator("#pfretry").is_visible()
            # recover: unpatch rendering, un-fail the fetch, retry the load
            pg.evaluate("(window.__renderUrgent = function(){}, undefined)")
            state["fail"] = False
            pg.locator("#pfretry").click()
            pg.wait_for_function("window.__permitsLoaded === true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert errors == []
    finally:
        srv.shutdown()


# #757: wraps the permit filter-link restore so the page-specific extra restore
# (expanded/group state) throws on its first invocation. The standard controls
# (pfq etc.) are set before that throw, so a pre-apply post-install failure
# leaves the restored filter values in place for the catch's replay.
_PATCH_EXTRA_RESTORE_ONCE = """
(function(){
  var real;
  Object.defineProperty(window, 'GinotFilterLinks', {
    configurable: true,
    get: function(){ return real; },
    set: function(v){
      var orig = v.register;
      real = {register: function(name, controls, extra){
        if(name === 'permit' && extra && extra.restore){
          var origExtra = extra.restore, first = true;
          extra = Object.assign({}, extra, {restore: function(p, n){
            if(first){ first = false; throw new Error('synthetic extra-restore failure'); }
            return origExtra(p, n);
          }});
        }
        return orig(name, controls, extra);
      }, build: v.build};
    }
  });
})();
"""


def test_publication_success_restores_stranded_url_state(tmp_path, browser, request):
    # #757: full-load post-install fails before apply() (the permit extra
    # restore throws once), leaving pendingUrlState stranded behind a render
    # retry. A later publications success must complete the deferred restore
    # before clearing the retry - clearing it without the restore hides the
    # only re-run path and leaves the shared-link controls disabled forever.
    # The same test pins the full-load catch's pre-apply filter replay: the
    # restored pfq value filters rows even though runFullPostInstall's own
    # apply() never ran.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script(_PATCH_EXTRA_RESTORE_ONCE)

            def hold_pubs(route):
                # publications_active.json must resolve only after the failed
                # full load surfaced its render retry and the stranded-state
                # assertions below ran (releasing earlier races the cleanup).
                # The release gate is page-side: blocking on a threading
                # primitive here would freeze the sync event loop.
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            # pre-apply replay pin: the restored query filters the installed
            # rows even though runFullPostInstall's apply() never ran.
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr").count() == 33
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            # the retry stays up while the URL state is pending
            assert pg.locator("#copy-permit-link").is_disabled()
            # publications evidence arrives and renders cleanly: the retry is
            # superseded only after the stranded URL state is restored.
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfrenderretry").count() == 0
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


# #757: installs a switchable throwing __renderUrgent wrapper before any page
# script runs. Patching via evaluate() from a route handler races the full
# load: the handler can land after runFullPostInstall already ran (seen in
# CI), and the render failure never happens.
_PATCH_RENDER_URGENT_THROW_SWITCH = """
(function(){
  var real;
  window.__renderShouldThrow = true;
  Object.defineProperty(window, '__renderUrgent', {
    configurable: true,
    get: function(){ return function(){ if(window.__renderShouldThrow) throw new Error('synthetic'); return real && real(); }; },
    set: function(v){ real = v; }
  });
})();
"""


def test_publication_success_supersedes_render_failure_with_url_state(
    tmp_path, browser, request
):
    # #757: intended-behavior pin - with a shared-link filter active, a
    # post-apply render failure (throwing __renderUrgent, after the URL state
    # was already restored) is cleared by a later successful publications
    # re-render, and the restored filter stays in effect.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script(_PATCH_RENDER_URGENT_THROW_SWITCH)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                # Same page-side release gate as the stranded-state test:
                # continuing right after the flag flips races the assertions.
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.input_value("#pfq") == "ייחודי"
            pg.evaluate(
                "window.__renderShouldThrow = false; window.__releasePubs = true"
            )
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfrenderretry").count() == 0
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


def test_early_publications_do_not_consume_pending_url_state(
    tmp_path, browser, request
):
    # #757 (CodeRabbit): a publications response that lands before the full
    # permits load must not consume the pending URL-state restore: group chips
    # introduced only by the full rows (ensureGroupChips, #622) fail validation
    # against the subset, silently dropping the link's group selection.
    srv, url = _lazy_site(tmp_path)
    # One full-list-only row carries a status no group maps (#521: unmapped is
    # fail-visible). Its chip exists only after ensureGroupChips runs on the
    # full rows.
    frag = tmp_path / "site" / "permits.html"
    html = frag.read_text()
    old = "data-group='review' data-scope="
    assert html.count(old) >= 1
    frag.write_text(
        html.replace(
            "data-status='שולמה מקדמה'", "data-status='סטטוס חדש לגמרי'", 1
        ).replace(old, "data-group='unmapped' data-scope=", 1)
    )
    try:
        with recorded_page(browser, request) as (pg, errors):

            def hold_full(route):
                # publications resolve while the full load is still in flight
                pg.wait_for_function(
                    "window.__permitPublicationEvidenceLoaded === true"
                )
                route.continue_()

            pg.route("**/permits.html", hold_full)
            pg.goto(url + "?filters=1&permit.groups=unmapped")
            pg.wait_for_function("window.__permitsLoaded === true")
            # the deferred restore ran against the full rows: the unmapped
            # chip was added by ensureGroupChips, then selected by the link.
            assert pg.locator(".chip[data-group='unmapped'].sel").count() == 1
            assert pg.locator("#permits-table tbody tr:not(.filtered-out)").count() == 1
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert errors == []
    finally:
        srv.shutdown()


# #759: makes permit-link restore() throw for the first window.__restoreThrowsLeft
# invocations (the page scripts live in an IIFE, so restore itself - reached
# through the GinotFilterLinks registrar, an assignment the init script can
# intercept - is the only fault point ahead of apply()). Each test arms the
# count with its own init script before this one.
_PATCH_PERMIT_RESTORE_THROW_N = """
(function(){
  var real;
  Object.defineProperty(window, 'GinotFilterLinks', {
    configurable: true,
    get: function(){ return real; },
    set: function(v){
      var orig = v.register;
      real = {register: function(name, controls, extra){
        var link = orig(name, controls, extra);
        if(name === 'permit' && link && link.restore){
          var origRestore = link.restore;
          link.restore = function(p, n){
            if(window.__restoreThrowsLeft > 0){
              window.__restoreThrowsLeft--;
              throw new Error('synthetic restore failure');
            }
            return origRestore(p, n);
          };
        }
        return link;
      }, build: v.build};
    }
  });
})();
"""


def test_publication_retry_rerun_restores_pending_url_state(tmp_path, browser, request):
    # #759: pins the restore line inside the publications catch retry-rerun.
    # restore() throws twice: the post-install attempt (stranding the pending
    # URL state behind a render retry) and the first publications success
    # render (its catch shows the retry bound to the publications rerun). The
    # pending state must survive both failures - controls stay disabled -
    # and clicking the retry must run the rerun's own restore.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script("window.__restoreThrowsLeft = 2")
            pg.add_init_script(_PATCH_PERMIT_RESTORE_THROW_N)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.locator("#copy-permit-link").is_disabled()
            # publications evidence arrives; its render fails on the restore,
            # which must leave the state pending: retry stays up, controls
            # stay disabled.
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded === true")
            pg.wait_for_function("window.__restoreThrowsLeft === 0")
            assert pg.locator("#pfrenderretry").is_visible()
            assert pg.locator("#copy-permit-link").is_disabled()
            # the retry rerun is the publications callback: it must restore.
            pg.locator("#pfrenderretry").click()
            pg.wait_for_function("window.__permitsRenderFailed === false")
            assert pg.locator("#pfload").inner_text() == ""
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert pg.input_value("#pfq") == "ייחודי"
            assert pg.locator("#permits-table tbody tr.filtered-out").count() > 0
            assert errors == []
    finally:
        srv.shutdown()


# #759: observes the table and the filter control at the __renderUrgent hook,
# which the publications success path calls immediately after apply().
_OBSERVE_AT_RENDER_URGENT = """
window.__renderUrgent = function(){
  window.__pfqAtRenderUrgent = document.getElementById('pfq').value;
  window.__rowsVisibleAtRenderUrgent =
    document.querySelectorAll('#permits-table tbody tr:not(.filtered-out)').length;
};
"""


def test_publication_restore_runs_before_apply(tmp_path, browser, request):
    # #759: pins the restore-before-apply() ordering in the publications
    # success path: the restored controls must filter the render that apply()
    # produces. restore() throws once (post-install), so the controls stay
    # unset until the publications restore; at the post-apply __renderUrgent
    # hook the restored query must already be filtering rows. Were restore
    # moved after apply(), apply() would render with empty controls and the
    # hook would observe an unfiltered table.
    srv, url = _lazy_site(tmp_path)
    try:
        with recorded_page(browser, request) as (pg, errors):
            pg.add_init_script("window.__restoreThrowsLeft = 1")
            pg.add_init_script(_PATCH_PERMIT_RESTORE_THROW_N)

            def hold_pubs(route):
                pg.wait_for_function("window.__permitsRenderFailed === true")
                pg.wait_for_function("window.__releasePubs === true")
                route.continue_()

            pg.route("**/publications_active.json", hold_pubs)
            pg.goto(url + "?filters=1&permit.groups=review&permit.pfq=ייחודי")
            pg.wait_for_function("window.__permitsRenderFailed === true")
            pg.evaluate(_OBSERVE_AT_RENDER_URGENT)
            pg.evaluate("window.__releasePubs = true")
            pg.wait_for_function("window.__permitsRenderFailed === false")
            pg.wait_for_function("window.__permitPublicationEvidenceLoaded === true")
            assert pg.evaluate("window.__pfqAtRenderUrgent") == "ייחודי"
            # exactly the one review-group row matching the restored query is
            # visible; an apply() before the restore (default chips, empty
            # query) would have left the 3 default objection rows visible
            assert pg.evaluate("window.__rowsVisibleAtRenderUrgent") == 1
            assert not pg.locator("#copy-permit-link").is_disabled()
            assert errors == []
    finally:
        srv.shutdown()
