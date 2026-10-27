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
    assert "awaiting independent and exact-head Claude reviews" in script
    assert "staged PR is not publication" in script
    assert "gh('pr', 'merge'" not in script
    assert "time.sleep" not in script
    assert "--admin" not in script
    assert "statusCheckRollup" not in script


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


def test_staged_pr_returns_without_check_poll_merge_or_dispatch(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('stage_publisher', root / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    for directory in ('data', 'docs'):
        (tmp_path / directory).mkdir()
    for path in module.FILES:
        (tmp_path / path).write_text('[]')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: None)
    calls = []
    def fake_gh(*args, payload=None):
        calls.append((args, payload))
        assert args[0] == 'api', 'publisher must not poll or merge a PR'
        path = args[1]
        if path.endswith('git/ref/heads/main'):
            return {'object': {'sha': 'a' * 40}}
        if '/git/commits/' in path:
            return {'tree': {'sha': 'b' * 40}}
        if path.endswith('/git/trees'):
            assert {entry['path'] for entry in payload['tree']} == set(module.FILES)
            assert all('private' not in entry['content'] for entry in payload['tree'])
            return {'sha': 'c' * 40}
        if path.endswith('/git/commits'):
            return {'sha': 'd' * 40}
        if path.endswith('/git/refs'):
            assert payload['ref'].startswith('refs/heads/publications/')
            return {}
        if path.endswith('/pulls'):
            return {'number': 7, 'html_url': 'https://example.test/pr/7'}
        raise AssertionError(json.dumps(args))
    monkeypatch.setattr(module, 'gh', fake_gh)
    module.main()
    assert len(calls) == 6
    assert 'staged PR is not publication' in capsys.readouterr().out
