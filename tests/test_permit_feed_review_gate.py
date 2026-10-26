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
    import os
    import subprocess

    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/permit-feed.yml').read_text()
    step = workflow.split('- name: Stop while a permit-feed data PR awaits review', 1)[1].split('- name:', 1)[0]
    shell = '\n'.join(line[10:] for line in step.split('run: |\n', 1)[1].splitlines())
    assert workflow.index('Stop while a permit-feed') < workflow.index('Install VPN transport')
    assert workflow.index('Stop while a permit-feed') < workflow.index('Bring up owner-operated')
    gh = tmp_path / 'gh'
    gh.write_text('#!/bin/bash\nprintf "%s\\n" "$*" > "$CALL_LOG"\nprintf "%s" "$PENDING_TEST"\nexit "$GH_EXIT"\n')
    gh.chmod(0o755)
    for pending, status, expected in [('', '0', 0), ('17\n18', '0', 1), ('', '42', 42)]:
        env = dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}',
                   GITHUB_REPOSITORY='test/repo', CALL_LOG=str(tmp_path / 'calls'),
                   PENDING_TEST=pending, GH_EXIT=status)
        result = subprocess.run(['bash', '-c', shell], env=env, capture_output=True,
                                text=True, check=False)
        assert result.returncode == expected, result.stderr
        call = (tmp_path / 'calls').read_text()
        assert '--paginate' in call
        assert 'state=open&base=main&per_page=100' in call
        assert 'startswith("permit-feed/")' in call
