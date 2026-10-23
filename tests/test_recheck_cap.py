import re
from pathlib import Path

WF = (Path(__file__).resolve().parents[1] / ".github/workflows/permit-feed.yml").read_text(encoding="utf-8")


def test_daily_recheck_cap_fits_step_timeout():
    # Run 39804643780: 143 parcels did not finish in 60 min (>25 s/parcel observed).
    m = re.search(r"--tier active --cap (\d+) --stale-before", WF)
    assert m, "daily re-check step not found"
    cap = int(m.group(1))
    assert cap * 40 <= 60 * 60, f"cap {cap} x 40s exceeds the 60 minute step limit"


def test_publish_merges_blocked_green_pr_with_admin():
    # Runs 39755426256 / 39804643780 failed on BLOCKED (required review).
    assert 'gh pr merge "$PR" --squash --admin --delete-branch' in WF
    assert '"$STATE" = "BLOCKED"' in WF
    assert "grep -c -E \"pending|fail|queued\"" in WF


def test_audit_result_merges_blocked_green_pr_with_admin():
    # Run 39879582801: green checks, BLOCKED by the required review, step exit 1.
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/audit-result.yml").read_text(encoding="utf-8")
    assert 'gh pr merge "$PR" --squash --admin --delete-branch' in wf
    assert 'if [ "$STATE" = BLOCKED ]' in wf
    assert 'grep -c -E "pending|fail|queued"' in wf
