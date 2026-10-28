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
    ("permit-feed.yml", "permit-feed", "PERMIT_FEED_ENABLED", "permit-feed/"),
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
    checkout = next(s for s in guard['steps'] if 'actions/checkout@' in s.get('uses', ''))
    assert checkout['with']['persist-credentials'] is False
    notice = next(s for s in guard['steps'] if '::notice::' in s.get('run', ''))
    assert notice['if'] == "${{ steps.guard.outputs.pending == 'true' }}"
    assert notice['env']['PENDING_PRS'] == '${{ steps.guard.outputs.pending_prs }}'
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
        if name == "mavat-watch.yml" and override == "!cancelled()":
            continue
        checked = cond.replace("!cancelled()", "") if override == "cancelled()" else cond
        assert override not in checked
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
    for name in ("weekly-refresh.yml", "mirror-ingest.yml", "permit-feed.yml"):
        cond = load(name)["jobs"][CASES[[c[0] for c in CASES].index(name)][1]]["if"]
        assert "||" not in cond


@pytest.mark.parametrize('name', ['weekly-refresh.yml', 'mavat-watch.yml'])
def test_entire_workflow_serializes_pending_check_and_data(name):
    assert load(name)['concurrency'] == {'group': name.removesuffix('.yml'),
                                        'cancel-in-progress': False}


def test_discover_skips_guard_and_explicitly_handles_skipped_dependency():
    doc = load('mavat-watch.yml')['jobs']
    assert doc['pending']['if'] == "${{ vars.MAVAT_WATCH_ENABLED != 'false' && inputs.mode != 'discover' }}"
    assert '!cancelled()' in doc['mavat-watch']['if']
    assert "needs.pending.result == 'success'" in doc['mavat-watch']['if']


def test_mavat_job_condition_truth_table_preserves_fail_closed():
    from itertools import product

    condition = load('mavat-watch.yml')['jobs']['mavat-watch']['if'][3:-2].strip()
    for disabled, cancelled, mode, result, pending in product(
        [False, True], [False, True], ['discover', 'check', ''],
        ['success', 'failure', 'skipped', 'cancelled'], ['false', 'true', ''],
    ):
        expression = condition
        values = {
            'cancelled()': cancelled,
            'vars.MAVAT_WATCH_ENABLED': 'false' if disabled else 'true',
            'inputs.mode': mode,
            'needs.pending.result': result,
            'needs.pending.outputs.pending': pending,
        }
        for token, value in values.items():
            expression = expression.replace(token, repr(value))
        expression = expression.replace('!cancelled', 'not cancelled')
        expression = expression.replace('!False', 'not False').replace('!True', 'not True')
        expression = expression.replace('&&', 'and').replace('||', 'or')
        actual = eval(expression, {'__builtins__': {}}, {})
        expected = not disabled and not cancelled and (
            mode == 'discover' or (result == 'success' and pending == 'false'))
        assert actual == expected, (disabled, cancelled, mode, result, pending)


def test_discover_only_probes_get_endpoints_and_cannot_stage_prs():
    import ast

    source = (ROOT / 'scripts/vpn/mavat_discover.py').read_text()
    probe = next(n for n in ast.parse(source).body
                 if isinstance(n, ast.FunctionDef) and n.name == 'probe')
    command = next(n.value for n in probe.body
                   if isinstance(n, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == 'cmd' for t in n.targets))
    constants = [n.value for n in command.elts if isinstance(n, ast.Constant)]
    assert constants[0] == 'curl'
    assert not {'-X', '--request', '-d', '--data', '--data-raw', '--data-binary',
                '-F', '--form', '-T', '--upload-file'} & set(constants)
    assert not any(token in source for token in ['gh pr', 'git push', 'gh workflow'])
    steps = load('mavat-watch.yml')['jobs']['mavat-watch']['steps']
    writers = [s for s in steps if 'gh pr create' in s.get('run', '')
               or 'git push' in s.get('run', '')]
    assert len(writers) == 1
    assert writers[0]['if'] == "${{ env.MODE == 'check' && success() }}"


@pytest.mark.parametrize('case', [c for c in CASES if c[0] != 'mavat-watch.yml'])
def test_non_mavat_status_override_mutation_is_rejected(monkeypatch, case):
    from copy import deepcopy

    name, job, var, prefix = case
    mutated = deepcopy(load(name))
    mutated['jobs'][job]['if'] = mutated['jobs'][job]['if'].replace(
        '${{ ', '${{ !cancelled() && ', 1)
    original_load = load
    monkeypatch.setitem(test_data_job_runs_only_after_a_false_verdict.__globals__,
                        'load', lambda target: mutated if target == name else original_load(target))
    with pytest.raises(AssertionError):
        test_data_job_runs_only_after_a_false_verdict(name, job, var, prefix)
