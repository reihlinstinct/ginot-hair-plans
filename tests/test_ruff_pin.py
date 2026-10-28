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


def test_ruff_pinned_to_one_version_in_linting_workflows():
    versions = set()
    assert _ruff_installs((WORKFLOWS / 'ci.yml').read_text()), 'CI must install Ruff'
    for path in WORKFLOWS.glob('*.yml'):
        name = path.name
        installs = _ruff_installs(path.read_text(encoding="utf-8"))
        for tok in installs:
            m = re.fullmatch(r"ruff==(\d+\.\d+\.\d+)", tok)
            assert m, f"{name}: ruff is not pinned exactly ({tok!r})"
            versions.add(m.group(1))
    assert len(versions) == 1, f"ruff versions differ across workflows: {versions}"
