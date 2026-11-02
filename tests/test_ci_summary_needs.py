"""The Run summary gate must keep every blocking job in its needs list (#769).

The gate fails closed on any failed/cancelled need, so a job silently
dropped from the list would leave the gate without it.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_summary_gate_needs_cover_every_blocking_job():
    doc = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = doc["jobs"]
    needs = set(jobs["summary"]["needs"])
    # pip-audit (#125/#764) must stay in the fail-closed gate.
    assert "pip-audit" in needs
    # The informational 3.15 leg must never gate: it is allowed to fail.
    assert "py315" not in needs
    # Every job that is neither the gate itself nor explicitly exempt
    # (the informational py315 leg, report-only mypy) must be gated.
    exempt_from_gate = {"py315", "mypy", "summary"}
    ungated = set(jobs) - needs - exempt_from_gate
    assert not ungated, f"jobs missing from the summary needs list: {ungated}"
