"""Tests for the Actions minute budget reporter (issue #680)."""

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "actions_budget", ROOT / "scripts" / "ci" / "actions_budget.py"
)
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)

CFG = {
    "monthly_private_minutes_included": 2000,
    "warn_at_percent": 50,
    "stop_at_percent": 80,
    "per_task_minutes": 60,
    "minute_multipliers": {"Linux": 1, "Windows": 2, "macOS": 10},
}


def item(repo, minutes, sku="Actions Linux", product="actions", unit="Minutes"):
    return {"product": product, "sku": sku, "unitType": unit,
            "quantity": minutes, "repositoryName": repo}


def test_only_private_repo_actions_minutes_count():
    items = [
        item("private-a", 100),
        item("public-b", 5000),
        item("private-a", 50, product="packages"),
        item("private-a", 30, sku="Actions storage", unit="GigabyteHours"),
    ]
    assert ab.private_minutes(items, {"private-a"}, CFG["minute_multipliers"]) == {"private-a": 100}


def test_api_shaped_items_match_case_insensitively_and_by_full_name():
    items = [
        item("owner/private-a", 40, product="Actions", unit="minutes"),
        item("private-a", 10),
        item("owner/public-b", 500),
    ]
    got = ab.private_minutes(items, {"owner/private-a"}, CFG["minute_multipliers"])
    assert got == {"private-a": 50}


def test_repos_not_private_today_are_reported_not_counted():
    items = [item("was-private", 300), item("priv", 20), item("owner/gone", 5, product="Actions", unit="Minutes")]
    other = ab.uncounted_minutes(items, {"priv"}, CFG["minute_multipliers"])
    assert other == {"was-private": 300, "gone": 5}
    assert ab.private_minutes(items, {"priv"}, CFG["minute_multipliers"]) == {"priv": 20}


def test_uncounted_minutes_apply_runner_multipliers():
    items = [item("went-public", 200, sku="Actions macOS 3-core")]
    assert ab.uncounted_minutes(items, set(), CFG["minute_multipliers"]) == {"went-public": 2000}


def test_macos_minutes_use_the_multiplier():
    items = [item("app", 10, sku="Actions macOS 3-core"), item("app", 10)]
    assert ab.private_minutes(items, {"app"}, CFG["minute_multipliers"]) == {"app": 110}


@pytest.mark.parametrize("total,state", [
    (0, "ok"), (999, "ok"), (1000, "warn"), (1599, "warn"), (1600, "stop"), (2500, "stop"),
])
def test_thresholds(total, state):
    assert ab.classify(total, CFG) == state


def test_config_in_repo_is_valid_and_ordered():
    cfg = ab.load_config()
    assert 0 < cfg["warn_at_percent"] < cfg["stop_at_percent"] <= 100
    assert cfg["per_task_minutes"] > 0


def test_bad_config_rejected(tmp_path):
    bad = tmp_path / "b.json"
    bad.write_text(json.dumps({**CFG, "warn_at_percent": 90}))
    with pytest.raises(ValueError):
        ab.load_config(bad)


WORKFLOW = """name: X
on: push
jobs:
  with-timeout:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - run: echo hi
  without:
    runs-on: ubuntu-24.04
    steps:
      - run: echo hi
  also-with:
    timeout-minutes: 5
    runs-on: ubuntu-24.04
"""


def test_jobs_without_timeout_found():
    assert ab.jobs_without_timeout(WORKFLOW) == ["without"]


def test_step_level_timeout_does_not_count_as_job_timeout():
    text = "jobs:\n  j:\n    runs-on: x\n    steps:\n      - run: a\n        timeout-minutes: 3\n"
    assert ab.jobs_without_timeout(text) == ["j"]


def test_commented_jobs_header_and_yaml_extension(tmp_path):
    text = "jobs: # build jobs\n  j:\n    runs-on: x\n"
    assert ab.jobs_without_timeout(text) == ["j"]
    (tmp_path / "a.yaml").write_text(text)
    (tmp_path / "b.yml").write_text("jobs:\n  k:\n    timeout-minutes: 3\n")
    assert ab.check_timeouts(tmp_path) == {"a.yaml": ["j"]}


def test_reusable_workflow_call_job_is_skipped():
    assert ab.jobs_without_timeout("jobs:\n  c:\n    uses: ./.github/workflows/x.yml\n") == []


def test_no_jobs_block():
    assert ab.jobs_without_timeout("name: x\non: push\n") == []


def test_cli_stop_exit_code(tmp_path, capsys):
    usage = tmp_path / "u.json"
    usage.write_text(json.dumps({"usageItems": [item("p", 1700)]}))
    code = ab.main(["--usage-file", str(usage), "--private-repo", "p"])
    assert code == 2
    assert "STOP" in capsys.readouterr().out


def test_cli_ok_exit_code(tmp_path):
    usage = tmp_path / "u.json"
    usage.write_text(json.dumps({"usageItems": [item("p", 10), item("pub", 9999)]}))
    assert ab.main(["--usage-file", str(usage), "--private-repo", "p"]) == 0


def test_usage_file_without_private_repo_is_rejected(tmp_path):
    usage = tmp_path / "u.json"
    usage.write_text(json.dumps({"usageItems": [item("p", 1700)]}))
    with pytest.raises(SystemExit) as exc:
        ab.main(["--usage-file", str(usage)])
    assert exc.value.code == 2


def test_live_requires_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        ab.main(["--live", "--year", "2026", "--month", "10"])
