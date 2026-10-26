from pathlib import Path


def test_watch_uses_checked_text_only_pr_and_preserves_outputs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/rishui-publish-watch.yml").read_text()
    script = (root / "scripts/ci/publish_publications.py").read_text()
    assert "git push" not in workflow
    assert "REFRESH_DISPATCH_TOKEN" in workflow
    assert "publish_publications.py" in workflow
    assert "data/publications_active.json" in workflow.split("path: |")[1]
    assert "/tmp/publish-new.json" in workflow.split("path: |")[1]
    assert "reuse_probe_run_id" in workflow
    assert "git/trees" in script
    assert "if checks_pass(checks)" in script
    assert "--match-head-commit" in script
    assert "--admin" not in script
    assert "FAILURE" in script


def test_check_gate_waits_for_complete_expected_set():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("publisher", root / "scripts/ci/publish_publications.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not module.checks_pass([{"name": "worker", "conclusion": "SUCCESS"}])
    checks = [{"name": name, "conclusion": "SUCCESS"} for name in module.EXPECTED_CHECKS]
    assert module.checks_pass(checks)
    checks.append({"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS"})
    assert module.checks_pass(checks)
    checks[-1]["state"] = "PENDING"
    assert not module.checks_pass(checks)
    checks.pop()
    checks[0]["conclusion"] = "FAILURE"
    assert not module.checks_pass(checks)


def test_reuse_requires_successful_probe_identity():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/rishui-publish-watch.yml").read_text()
    assert 'r["status"] == "completed"' in workflow
    assert 'r["conclusion"] == "success"' in workflow
    assert 'r["path"].split("@", 1)[0] == ".github/workflows/rishui-publish-probe.yml"' in workflow


def test_diff_step_propagates_failure_through_tee():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/rishui-publish-watch.yml").read_text()
    step = workflow.split("- name: Diff against baseline and write alert file")[1].split("- name:")[0]
    assert "set -o pipefail" in step
    result = subprocess.run(["bash", "-c", "set -o pipefail; false | tee /dev/null"], check=False)
    assert result.returncode != 0
