from pathlib import Path


def test_mavat_publish_updates_branch_then_waits_for_clean_before_merge():
    workflow = (Path(__file__).parent.parent / '.github/workflows/mavat-watch.yml').read_text()
    update = workflow.index('gh pr update-branch "$PR"')
    check = workflow.index('gh pr view "$PR" --json mergeStateStatus', update)
    merge = workflow.index('gh pr merge "$PR" --squash --delete-branch', check)
    assert update < check < merge
    wait = workflow[check:merge]
    assert '"$STATE" = "CLEAN"' in wait
    assert '"$STATE" = "DIRTY"' in wait
    assert '"$i" = "45"' in wait
    assert '--admin' not in workflow
