from pathlib import Path


def test_permit_publication_never_merges_or_bypasses_review():
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/permit-feed.yml').read_text()
    publish = workflow.split('- name: Publish changes as a PR', 1)[1].split('- name: Dispatch read-only', 1)[0]
    assert 'gh pr create' in publish
    assert 'gh pr merge' not in publish
    assert '--admin' not in publish
    assert 'awaiting independent and exact-head Claude reviews' in publish
    # Audit and enrichment successor must not treat PR creation as publication.
    assert workflow.count("steps.publish.outputs.merged == 'true'") == 2


def test_no_change_and_created_pr_both_explicitly_stop_publication_successors():
    import subprocess
    import tempfile

    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/permit-feed.yml').read_text()
    publish = workflow.split('        id: publish', 1)[1].split('- name: Dispatch read-only', 1)[0]
    no_change = publish.split('if git diff --quiet data/; then', 1)[1].split('          fi', 1)[0]
    # Execute the actual no-change shell body without running git or network.
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'output'
        result = subprocess.run(['bash', '-eu', '-c', no_change],
                                env={'GITHUB_OUTPUT': str(output)}, check=False)
        assert result.returncode == 0
        assert output.read_text().strip() == 'merged=false'
    created = publish.split('echo "opened $PR"', 1)[1]
    assert 'echo "merged=false" >> "$GITHUB_OUTPUT"' in created
    assert 'merged=true' not in publish


def test_pending_publication_guard_stops_before_network_and_fails_closed(tmp_path):
    import json
    import os
    import subprocess

    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/permit-feed.yml').read_text())
    pending = workflow['jobs']['pending']
    data = workflow['jobs']['permit-feed']
    assert data['needs'] == 'pending'
    assert data['if'] == "${{ vars.PERMIT_FEED_ENABLED != 'false' && (needs.pending.outputs.pending == 'false') }}"
    guard = next(s for s in pending['steps'] if s.get('id') == 'guard')
    notice = next(s for s in pending['steps'] if '::notice::' in s.get('run', ''))
    assert notice['if'] == "${{ steps.guard.outputs.pending == 'true' }}"
    assert notice['env']['PENDING_PRS'] == '${{ steps.guard.outputs.pending_prs }}'
    # Every VPN step is in the dependent data job, never the guard job.
    assert 'l2tp' not in str(pending)
    assert any('Bring up owner-operated' in s.get('name', '') for s in data['steps'])
    gh = tmp_path / 'gh'
    gh.write_text('#!/bin/bash\nprintf "%s\n" "$*" > "$CALL_LOG"\nprintf "%s" "$PENDING_TEST"\nexit "$GH_EXIT"\n')
    gh.chmod(0o755)

    def pr(repo, ref):
        return {'number': 17, 'head': {'ref': ref, 'repo': {'full_name': repo}}}

    cases = [(json.dumps([]), '0', 'false'),
             (json.dumps([pr('test/repo', 'permit-feed/batch')]), '0', 'true'),
             (json.dumps([pr('fork/repo', 'permit-feed/batch')]), '0', 'false'),
             (json.dumps([pr('test/repo', 'unrelated')]), '0', 'false'),
             (json.dumps([]), '42', None), ('not json', '0', None)]
    for i, (body, status, verdict) in enumerate(cases):
        output = tmp_path / f'output-{i}'
        env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}',
                   GITHUB_REPOSITORY='test/repo', CALL_LOG=str(tmp_path / 'calls'),
                   PENDING_TEST=body, GH_EXIT=status, GITHUB_OUTPUT=str(output))
        result = subprocess.run(['bash', '-eu', '-c', guard['run']], cwd=root,
                                env=env, capture_output=True, text=True, check=False)
        assert result.returncode == (1 if verdict is None else 0), result.stderr
        call = (tmp_path / 'calls').read_text()
        assert 'state=open&per_page=100&page=1' in call
        if verdict is None:
            assert not output.exists()
            assert 'pending=' not in result.stdout
            assert 'failed closed' in result.stderr
        else:
            assert f'pending={verdict}' in output.read_text().splitlines()
            if verdict == 'true':
                notice_result = subprocess.run(['bash', '-eu', '-c', notice['run']],
                                               env=dict(env, PENDING_PRS='17'),
                                               capture_output=True, text=True, check=False)
                assert notice_result.returncode == 0
                assert '::notice::data PR(s) 17' in notice_result.stdout
