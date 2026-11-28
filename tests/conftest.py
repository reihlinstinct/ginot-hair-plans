"""Shared pytest hooks (issue #422)."""

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        item._e2e_passed = rep.passed


# The generated pages carry a Content-Security-Policy meta without
# 'unsafe-eval'. Playwright's Page.wait_for_function evaluates its expression
# string with eval() inside the page, which that policy blocks, so the browser
# tests could not wait on page state. Poll with Page.evaluate instead: it runs
# over the DevTools protocol and is not subject to the page CSP, so the pages
# are still tested with the policy enforced (no bypass_csp).
#
# Playwright is optional for the unit tests, so the patch is installed from a
# hook at session start (not at collection time) and does nothing when
# Playwright is not installed (the browser test files skip themselves then).


def _csp_safe_wait_for_function(page_cls, timeout_error):
    import time

    def wait_for_function(self, expression, arg=None, *, timeout=None, polling=None):
        deadline = time.monotonic() + (30000 if timeout is None else timeout) / 1000
        step = (
            0.05 if not isinstance(polling, (int, float)) else max(polling, 10) / 1000
        )
        # JS truthiness, not Python's: an empty object or array is truthy in the
        # page but comes back as a falsy {} or [] here, so coerce in the page.
        if "=>" in expression or expression.lstrip().startswith("function"):
            wrapped = f"(...a) => !!({expression})(...a)"
        else:
            wrapped = f"() => !!({expression})"
        while True:
            if (
                self.evaluate(wrapped, arg)
                if arg is not None
                else self.evaluate(wrapped)
            ):
                return True
            if time.monotonic() >= deadline:
                raise timeout_error(f"wait_for_function timed out: {expression[:120]}")
            time.sleep(step)

    page_cls.wait_for_function = wait_for_function


def pytest_sessionstart(session):
    try:
        from playwright.sync_api import Page, TimeoutError
    except ImportError:  # no Playwright: the browser tests are skipped
        return
    _csp_safe_wait_for_function(Page, TimeoutError)
