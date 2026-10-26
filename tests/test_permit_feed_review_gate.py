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
