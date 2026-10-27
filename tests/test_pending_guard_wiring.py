"""#564: data workflows must not stack a second data PR while one awaits review.

Each scheduled data workflow runs the shared fail-closed guard
(scripts/ci/pending_data_pr.py) in a read-only ``pending`` job before any
fetch, VPN or tunnel, and its data job runs only when the guard reached
``pending=false``.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    # workflow, data job, kill-switch var, branch prefix the job pushes
    ("weekly-refresh.yml", "refresh", "WEEKLY_REFRESH_ENABLED", "weekly-refresh/"),
    ("mavat-watch.yml", "mavat-watch", "MAVAT_WATCH_ENABLED", "mavat-check/"),
    ("mirror-ingest.yml", "mirror-ingest", "MIRROR_INGEST_ENABLED", "mirror-ingest/"),
]


def load(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


@pytest.mark.parametrize("name,job,var,prefix", CASES)
def test_guard_job_is_read_only_and_uses_the_pushed_prefix(name, job, var, prefix):
    guard = load(name)["jobs"]["pending"]
    assert guard["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert f"vars.{var} != 'false'" in guard["if"]
    assert guard["outputs"]["pending"] == "${{ steps.guard.outputs.pending }}"
    step = next(s for s in guard["steps"] if s.get("id") == "guard")
    assert step["run"] == (
        f'python3 scripts/ci/pending_data_pr.py --repo "$GITHUB_REPOSITORY" --prefix {prefix}'
    )
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    # Guard steps never fetch, tunnel, push or use secrets.
    text = "\n".join(str(s) for s in guard["steps"])
    for forbidden in (
        "secrets.",
        "l2tp",
        "git push",
        "refresh.py",
        "mirror_ingest",
        "mavat_check",
    ):
        assert forbidden not in text
    # The prefix must be the one the data job actually pushes.
    runs = "\n".join(s.get("run", "") for s in load(name)["jobs"][job]["steps"])
    assert f'BRANCH="{prefix}' in runs


@pytest.mark.parametrize("name,job,var,prefix", CASES)
def test_data_job_runs_only_after_a_false_verdict(name, job, var, prefix):
    data = load(name)["jobs"][job]
    assert data["needs"] == "pending"
    cond = data["if"]
    assert f"vars.{var} != 'false'" in cond
    assert "needs.pending.outputs.pending == 'false'" in cond
    # No status override: a failed guard (fail closed) must skip the data job.
    for override in ("always()", "failure()", "cancelled()", "!cancelled()"):
        assert override not in cond
    assert "!= 'true'" not in cond


def test_only_mavat_discover_mode_bypasses_the_guard():
    """Discover mode only probes endpoints and never stages a PR."""
    cond = load("mavat-watch.yml")["jobs"]["mavat-watch"]["if"]
    assert "inputs.mode == 'discover' ||" in cond
    stage = next(
        s
        for s in load("mavat-watch.yml")["jobs"]["mavat-watch"]["steps"]
        if "gh pr create" in s.get("run", "")
    )
    assert "env.MODE == 'check'" in stage["if"]
    for name in ("weekly-refresh.yml", "mirror-ingest.yml"):
        cond = load(name)["jobs"][CASES[[c[0] for c in CASES].index(name)][1]]["if"]
        assert "||" not in cond
