"""Unit tests for the E2E evidence helpers (issue #422)."""

import pytest
from evidence import (
    artifact_root,
    browser_engine,
    evidence_dir,
    keep_heavy_evidence,
)


def test_default_root_is_gitignored_artifacts_dir():
    assert str(artifact_root(env={})) == "tests/.artifacts"


def test_root_override_via_env():
    assert str(artifact_root(env={"SITE_EVIDENCE_DIR": "/tmp/ev"})) == "/tmp/ev"


def test_engine_defaults_to_chromium():
    assert browser_engine(env={}) == "chromium"


def test_engine_accepts_webkit_case_insensitively():
    assert browser_engine(env={"SITE_BROWSER": "WebKit"}) == "webkit"


def test_engine_rejects_unknown():
    with pytest.raises(ValueError):
        browser_engine(env={"SITE_BROWSER": "firefox"})


def test_heavy_evidence_kept_on_failure():
    assert keep_heavy_evidence(passed=False, marked=False) is True


def test_heavy_evidence_kept_for_marked_success():
    assert keep_heavy_evidence(passed=True, marked=True) is True


def test_heavy_evidence_discarded_for_unmarked_success():
    assert keep_heavy_evidence(passed=True, marked=False) is False


def test_test_dir_scopes_by_engine_and_sanitizes_name():
    d = evidence_dir("/r", "chromium", "tests/test_site_browser.py::test_x[390-]")
    assert str(d) == "/r/chromium/test_x_390-"
