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
