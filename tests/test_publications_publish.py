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
    (tmp_path / 'data/publications_active.json').write_text(json.dumps([{'tik_num': '2026/0439.00', 'in_polygon': True, 'private_note': 'omit'}]))
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    processes = []
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: processes.append((a, kw)))
    calls = []
    def fake_gh(*args, payload=None):
        calls.append((args, payload))
        assert args[0] == 'api', 'publisher must not poll or merge a PR'
        path = args[-1]
        if '/pulls?' in path:
            return [[]]
        if path.endswith('git/ref/heads/main'):
            return {'object': {'sha': 'a' * 40}}
        if '/git/commits/' in path:
            return {'tree': {'sha': 'b' * 40}}
        if path.endswith('/git/trees'):
            assert {entry['path'] for entry in payload['tree']} == {'data/publications_active.json', 'data/publications_new_latest.json', 'docs/publications_active.json', 'docs/index.json', 'docs/permits-default.html'}
            projection = next(entry for entry in payload['tree'] if entry['path'] == 'docs/publications_active.json')
            assert 'private_note' not in projection['content']
            assert '2026/0439.00' in projection['content']
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
    assert len(calls) == 7
    assert processes == [((['python3', 'scripts/build_site_index.py', 'data', 'docs/index.json'],), {'check': True}),
                         ((['python3', 'scripts/render_permits_page.py', '--default-only'],), {'check': True})]
    assert 'staged PR is not publication' in capsys.readouterr().out


def test_main_pending_and_no_change_never_write(tmp_path, monkeypatch, capsys):
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('wait_publisher', root / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    for directory in ('data', 'docs'):
        (tmp_path / directory).mkdir()
    for path in module.FILES:
        (tmp_path / path).write_text('[]')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    processes = []
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: processes.append((a, kw)))
    for pending in (True, False):
        calls = []
        def gh(*args, _calls=calls, _pending=pending, **kwargs):
            _calls.append(args)
            assert args[0] == 'api'
            path = args[-1]
            if '/pulls?' in path:
                return [[{'number': 9, 'head': {'repo': {'full_name': 'synthetic/repo'}, 'ref': 'publications/1'}}]] if _pending else [[]]
            if path.endswith('git/ref/heads/main'):
                return {'object': {'sha': 'a' * 40}}
            if '/git/commits/' in path:
                return {'tree': {'sha': 'b' * 40}}
            if path.endswith('/git/trees'):
                return {'sha': 'b' * 40}  # unchanged, no commit/ref/PR creation
            raise AssertionError(args)
        monkeypatch.setattr(module, 'gh', gh)
        module.main()
        assert len(calls) == (1 if pending else 4)
        assert ('awaiting review' if pending else 'no publication changes') in capsys.readouterr().out
    assert all(call[0][0] in (['python3', 'scripts/build_site_index.py', 'data', 'docs/index.json'],
                              ['python3', 'scripts/render_permits_page.py', '--default-only']) for call in processes)
