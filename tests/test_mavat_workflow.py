from pathlib import Path


def test_mavat_publish_updates_branch_then_waits_for_clean_before_merge():
    workflow = (Path(__file__).parent.parent / '.github/workflows/mavat-watch.yml').read_text()
    update = workflow.index('gh pr update-branch "$PR"')
    check = workflow.index('gh pr view "$PR" --json mergeStateStatus', update)
    merge = workflow.index('gh pr merge "$PR" --squash', check)
    assert update < check < merge
    wait = workflow[check:merge]
    assert '"$STATE" = "CLEAN"' in wait
    assert '"$STATE" = "DIRTY"' in wait
    # 90-poll budget: update-branch restarts pull_request CI; the old 45-poll
    # budget missed a queue-delayed restart by 10s in run 39900080019 (#380).
    assert '"$i" = "90"' in wait
    # Since branch protection (22.10) requires a review the bot cannot give,
    # the only bypass is the single gated admin merge after every check is
    # green (#372/#375; same pattern as permit-feed/audit-result/mirror-ingest).
    assert '"$STATE" = "BLOCKED"' in wait
    assert 'gh pr checks "$PR"' in wait
    assert workflow.count('--admin') == 1
