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
try:
    from playwright.sync_api import Page as _Page
    from playwright.sync_api import TimeoutError as _PwTimeout
except ImportError:  # browser tests are skipped without playwright
    _Page = None

if _Page is not None:
    import time as _time

    def _wait_for_function(self, expression, arg=None, *, timeout=None, polling=None):
        deadline = _time.monotonic() + (30000 if timeout is None else timeout) / 1000
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
            if _time.monotonic() >= deadline:
                raise _PwTimeout(f"wait_for_function timed out: {expression[:120]}")
            _time.sleep(step)

    _Page.wait_for_function = _wait_for_function
