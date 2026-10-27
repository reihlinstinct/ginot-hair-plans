import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_publisher_pending_guard_pages_repo_prefix_and_fail_closed(monkeypatch):
    spec = importlib.util.spec_from_file_location('pending', ROOT / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def pr(number, repo, ref):
        return {'number': number, 'head': {'repo': {'full_name': repo}, 'ref': ref}}
    calls = []
    def fake(*args, **kwargs):
        calls.append(args)
        return [[pr(1, 'fork/repo', 'publications/1')],
                [pr(2, 'test/repo', 'other'), pr(3, 'test/repo', 'publications/3')]]
    monkeypatch.setattr(module, 'gh', fake)
    assert module.pending_publication_prs('test/repo') == [3]
    assert '--paginate' in calls[0] and '--slurp' in calls[0]
    monkeypatch.setattr(module, 'gh', lambda *a: None)
    with pytest.raises(RuntimeError, match='Invalid'):
        module.pending_publication_prs('test/repo')
    def error(*a):
        raise RuntimeError('API unavailable')
    monkeypatch.setattr(module, 'gh', error)
    with pytest.raises(RuntimeError, match='API unavailable'):
        module.pending_publication_prs('test/repo')


def test_workflow_guard_stops_before_network_and_serializes():
    text = (ROOT / '.github/workflows/rishui-publish-watch.yml').read_text()
    assert 'group: rishui-publish-watch' in text
    assert 'cancel-in-progress: false' in text
    assert text.index('Stop while a publication') < text.index('actions/checkout')
    assert text.index('Stop while a publication') < text.index('Fetch active publications')
    assert '--paginate' in text
    assert '.head.repo.full_name == $repo' in text
    assert 'startswith("publications/")' in text


def test_pending_publication_guard_stops_before_network_and_fails_closed(tmp_path):
    import json
    import os
    import subprocess

    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/rishui-publish-watch.yml').read_text()
    step = workflow.split('- name: Stop while a publication data PR awaits review', 1)[1].split('      - uses:', 1)[0]
    shell = '\n'.join(line[10:] for line in step.split('run: |\n', 1)[1].splitlines())
    assert workflow.index('Stop while a publication') < workflow.index('Fetch active publications list')
    gh = tmp_path / 'gh'
    gh.write_text('#!/bin/bash\nprintf "%s\\n" "$*" > "$CALL_LOG"\nprintf "%s" "$PENDING_TEST"\nexit "$GH_EXIT"\n')
    gh.chmod(0o755)
    def pr(repo, ref):
        return {'number': 17, 'head': {'ref': ref, 'repo': {'full_name': repo}}}

    cases = [([], '0', 0), ([pr('test/repo', 'publications/batch')], '0', 1),
             ([pr('fork/repo', 'publications/batch')], '0', 0),
             ([pr('test/repo', 'unrelated')], '0', 0),
             ([], '42', 42)]
    for pending, status, expected in cases:
        env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}',
                   GITHUB_REPOSITORY='test/repo', CALL_LOG=str(tmp_path / 'calls'),
                   PENDING_TEST=json.dumps(pending), GH_EXIT=status)
        result = subprocess.run(['bash', '-c', shell], env=env, capture_output=True,
                                text=True, check=False)
        assert result.returncode == expected, result.stderr
        call = (tmp_path / 'calls').read_text()
        assert '--paginate' in call
        assert 'state=open&base=main&per_page=100' in call
    assert '.head.repo.full_name == $repo' in shell
    assert 'startswith("publications/")' in shell
