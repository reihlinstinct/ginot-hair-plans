"""#564: fetched weekly data must wait for review, never self-publish."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_weekly_refresh_stages_data_without_self_merge_or_deployment():
    workflow = (ROOT / '.github/workflows/weekly-refresh.yml').read_text()
    assert 'gh pr create' in workflow
    assert 'Requires independent review, exact-head Claude review and green CI' in workflow
    assert 'awaiting independent and exact-head Claude reviews' in workflow
    for forbidden in ('gh pr merge', '--admin', 'gh pr update-branch',
                      '/approve', '/pages/builds', 'refs/heads/mirror',
                      '--force', 'gh workflow run'):
        assert forbidden not in workflow
    assert 'scripts/land_feed.py' in workflow
    assert 'python3 -u refresh.py' in workflow
    assert 'git push -u origin "$BRANCH"' in workflow


def test_weekly_refresh_regenerates_after_reconciliation_before_commit():
    workflow = (ROOT / '.github/workflows/weekly-refresh.yml').read_text()
    reset = workflow.index('git reset --hard origin/main')
    render = workflow.index('python3 scripts/ci/check_docs_fresh.py --write')
    check = workflow.index('python3 scripts/ci/check_docs_fresh.py\n', render)
    commit = workflow.index('git commit -m')
    assert reset < render < check < commit
