"""Ruff is pinned in every workflow that lints (issue #510).

ruff.toml selects no rules, so the active rule set is ruff's default for the
installed version. An unpinned install let a runner-side ruff upgrade start
flagging DTZ011 on main. Lint changes must arrive through a deliberate bump,
and every workflow that actually installs Ruff must run the same version.
"""

import pathlib
import re

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _ruff_installs(text):
    return [
        tok
        for line in text.splitlines()
        if "pip install" in line
        for tok in line.split()
        if re.match(r"ruff(\b|[=<>!~])", tok)
    ]


def _resolved_versions(name, text):
    versions = set()
    for tok in _ruff_installs(text):
        m = re.fullmatch(r"ruff==(\d+\.\d+\.\d+)", tok)
        if m:
            versions.add(m.group(1))
            continue
        m = re.fullmatch(r'ruff=="?\$(\w+)"?', tok)
        assert m, f"{name}: ruff is not pinned exactly ({tok!r})"
        var = m.group(1)
        # The pin variable must be defined at workflow level (two-space
        # indent); a job- or step-level definition could drift per job.
        env = re.search(rf"^  {var}: [\"']?(\d+\.\d+\.\d+)[\"']?\s*$", text, re.M)
        assert env, f"{name}: ruff pinned via ${var} but no workflow-level env defines it"
        versions.add(env.group(1))
    return versions


def test_ruff_pinned_to_one_version_in_linting_workflows():
    versions = set()
    assert _ruff_installs((WORKFLOWS / "ci.yml").read_text()), "CI must install Ruff"
    for path in WORKFLOWS.glob("*.yml"):
        versions |= _resolved_versions(path.name, path.read_text(encoding="utf-8"))
    assert len(versions) == 1, f"ruff versions differ across workflows: {versions}"
