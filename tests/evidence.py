"""Per-test E2E evidence capture helpers (issue #422).

Pure path/keep-decision logic, unit-tested without a browser. The browser
fixtures in test_site_browser.py call into this module.
"""

import os
import pathlib
import re

DEFAULT_ROOT = pathlib.Path("tests") / ".artifacts"


def artifact_root(env=None):
    """Evidence root directory; overridable via SITE_EVIDENCE_DIR."""
    env = os.environ if env is None else env
    raw = env.get("SITE_EVIDENCE_DIR")
    return pathlib.Path(raw) if raw else DEFAULT_ROOT


def browser_engine(env=None):
    """Playwright engine for the site browser tests: chromium or webkit."""
    env = os.environ if env is None else env
    engine = (env.get("SITE_BROWSER") or "chromium").strip().lower()
    if engine not in ("chromium", "webkit"):
        raise ValueError(f"SITE_BROWSER must be chromium or webkit, got {engine!r}")
    return engine


def _slug(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")[:120]


def evidence_dir(root, engine, nodeid):
    """tests/.artifacts/<engine>/<test slug>/ for one test's evidence."""
    return pathlib.Path(root) / _slug(engine) / _slug(nodeid.split("::")[-1])


def keep_heavy_evidence(passed, marked):
    """Video+trace are heavy: keep on failure, or on success for tests
    marked @pytest.mark.evidence (representative user-repro flows)."""
    return (not passed) or bool(marked)
