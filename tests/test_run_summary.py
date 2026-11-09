"""Regression contracts for the standalone CI run-summary entrypoint."""

import importlib.util
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "run_summary.py"


@pytest.fixture
def summary():
    spec = importlib.util.spec_from_file_location("run_summary_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_startup_regression_checks_keep_passing(summary):
    summary._self_test()


def test_standalone_entrypoint_without_pythonpath(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
    env.pop("PYTHONPATH", None)
    env["NEEDS_JSON"] = "{"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "No upstream jobs declared in `needs`." in result.stdout
    assert "No change range is available for this run." in result.stdout


def test_jobs_changes_and_coverage_still_render(summary, monkeypatch, tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": "abc", "after": "def"}))
    target = tmp_path / "summary.md"
    target.write_text("existing\n")
    coverage = tmp_path / "coverage.json"
    coverage.write_text(
        json.dumps({"mappings": [{"pattern": "src/**", "checks": ["test"]}]})
    )
    env = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_STEP_SUMMARY": str(target),
        "GITHUB_WORKFLOW": "CI",
        "NEEDS_JSON": json.dumps(
            {"test": {"result": "success"}, "lint": {"result": "skipped"}}
        ),
    }
    monkeypatch.setattr(summary.os, "environ", env)
    monkeypatch.setattr(summary, "MAP_PATH", str(coverage))
    monkeypatch.setattr(summary, "job_durations", lambda _: {"test": 65.0})
    monkeypatch.setattr(summary, "load_job_meta", lambda _: ({"lint": "a < b"}, {}))
    real_sh = summary.sh

    def sh(*args):
        if args[0] != "git":
            return real_sh(*args)  # startup regression checks still run
        if args[1] == "log":
            return b"deadbee <script>| subject\r forged"
        return b"M\x00src/x.py\x00A\x00other.txt\x00"

    monkeypatch.setattr(summary, "sh", sh)
    summary.main()
    result = target.read_text()
    assert result.startswith("existing\n## Run summary - CI")
    assert "| `test` | success | 1m 05s |" in result
    assert "runs only if a &lt; b" in result
    assert "What changed in this run (`abc..def`)" in result
    assert "&lt;script&gt;\\| subject  forged" in result
    assert "| src/x.py | modified | `test` |" in result
    assert "| other.txt | added | - |" in result
    assert "Changed without declared coverage" in result


def test_startup_failure_is_still_a_hard_stop(summary, monkeypatch, capsys):
    monkeypatch.setattr(summary, "md_escape", lambda _: "broken")
    with pytest.raises(SystemExit, match="self-test failed"):
        summary.main()
    assert capsys.readouterr().out == ""


def test_runtime_failure_still_degrades_without_failing_workflow(
    summary, monkeypatch, capsys
):
    data = sys.modules["run_summary_data"]

    def unavailable(_):
        raise RuntimeError("offline regression fixture")

    monkeypatch.setattr(data, "job_durations", unavailable)
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert (
        "run_summary: degraded: offline regression fixture" in capsys.readouterr().err
    )
