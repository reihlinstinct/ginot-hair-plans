"""The CI install lines must pin the tool extras identically (#772 follow-up).

The test jobs and the pip-audit appenv install ruff and pytest-cov; if
one line drifts (different version or a dropped pin), the audit no
longer covers what the tests run. The pins live in workflow-level env
vars so parity is structural - this test guards that property.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALL_RE = re.compile(r"pip(?:3)? install (?P<pkgs>.+)")


def _install_lines(doc):
    lines = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            for line in run.splitlines():
                m = INSTALL_RE.search(line)
                if m and "requirements.txt" in m.group("pkgs"):
                    lines.append(m.group("pkgs").strip())
    return lines


def test_tool_extras_pinned_identically_on_every_install_line():
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    env = doc["env"]
    assert env["RUFF_VERSION"] and env["PYTEST_COV_VERSION"]
    lines = [l for l in _install_lines(doc) if "ruff" in l or "pytest-cov" in l]
    assert len(lines) >= 3, "expected both test jobs and the appenv install"
    for pkgs in lines:
        assert "ruff==$RUFF_VERSION" in pkgs, pkgs
        assert "pytest-cov==$PYTEST_COV_VERSION" in pkgs, pkgs
        assert not re.search(r"ruff(?![=a-z-])", pkgs.replace("ruff==", "")), pkgs
        assert not re.search(
            r"pytest-cov(?![=a-z-])", pkgs.replace("pytest-cov==", "")
        ), pkgs
