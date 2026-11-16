"""Ruff is pinned in every workflow that lints (issue #510, hash-locked in #770).

ruff.toml selects no rules, so the active rule set is ruff's default for the
installed version. An unpinned install let a runner-side ruff upgrade start
flagging DTZ011 on main. Lint changes must arrive through a deliberate bump:
ci.yml installs Ruff from the hash-locked requirements-ci-tools.txt, the lock
pin must match the workflow's RUFF_VERSION env, and no workflow may install
Ruff directly (a second install path could drift).
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
LOCK = ROOT / "requirements-ci-tools.txt"


def _ruff_installs(text):
    return [
        tok
        for line in text.splitlines()
        if "pip install" in line or "pip3 install" in line
        for tok in line.split()
        if re.match(r"ruff(\b|[=<>!~])", tok)
    ]


def test_ci_installs_ruff_from_the_locked_tools_file():
    ci = (WORKFLOWS / "ci.yml").read_text()
    assert "requirements-ci-tools.txt" in ci, "CI must install Ruff"
    assert not _ruff_installs(ci), "ci.yml must not install ruff directly"
    env = re.search(
        r'^  RUFF_VERSION: ["\']?(\d+\.\d+\.\d+)["\']?\s*$', ci, re.MULTILINE
    )
    assert env, "ci.yml must define workflow-level RUFF_VERSION"
    lock = LOCK.read_text()
    pin = re.search(r"^ruff==(\d+\.\d+\.\d+)", lock, re.MULTILINE)
    assert pin, "requirements-ci-tools.txt must pin ruff==X.Y.Z"
    assert pin.group(1) == env.group(1), (
        f"ruff lock pin {pin.group(1)} != RUFF_VERSION {env.group(1)}"
    )


def test_no_workflow_installs_ruff_directly():
    for path in sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")]):
        assert not _ruff_installs(path.read_text(encoding="utf-8")), (
            f"{path.name}: install ruff via requirements-ci-tools.txt only"
        )
