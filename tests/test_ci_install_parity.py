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


def test_tool_extras_pinned_identically_on_every_install_line():
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    env = doc["env"]
    assert env["RUFF_VERSION"] and env["PYTEST_COV_VERSION"]
    # Covers standalone installs too (no requirements.txt on the line).
    lines = [
        line
        for job in doc["jobs"].values()
        for step in job.get("steps", [])
        for line in step.get("run", "").splitlines()
        if "pip install" in line and ("ruff" in line or "pytest-cov" in line)
    ]
    assert len(lines) >= 3, "expected both test jobs and the appenv install"
    for line in lines:
        assert 'ruff=="$RUFF_VERSION"' in line, line
        assert 'pytest-cov=="$PYTEST_COV_VERSION"' in line, line
        assert not re.search(r"ruff(?![=a-z-])", line.replace("ruff==", "")), line
        assert not re.search(
            r"pytest-cov(?![=a-z-])", line.replace("pytest-cov==", "")
        ), line


def test_pin_vars_defined_only_at_workflow_level():
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    pins = {"RUFF_VERSION", "PYTEST_COV_VERSION"}
    offenders = []
    for job_name, job in doc["jobs"].items():
        if pins & set(job.get("env", {})):
            offenders.append(f"job {job_name}")
        for step in job.get("steps", []):
            if pins & set(step.get("env", {})):
                offenders.append(f"step in {job_name}")
    assert not offenders, f"pin vars overridden outside workflow env: {offenders}"
