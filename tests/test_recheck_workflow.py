"""Tiered re-check C: permit-feed.yml wiring for mode=recheck (no network)."""
import pathlib

WF = (pathlib.Path(__file__).parent.parent / ".github/workflows/permit-feed.yml").read_text()


def test_recheck_mode_runs_selector_then_parcel_list():
    assert "recheck_select.py" in WF and "--parcel-list /tmp/recheck_parcels.json" in WF
    assert "recheck_tier" in WF


def test_recheck_does_not_use_offset_backfill_steps_or_schedule():
    assert WF.count("env.REQ_MODE != 'recheck'") >= 3  # batch params, scan, auditor
    # schedule list unchanged: only the existing four daily crons, none recheck-specific
    assert WF.count("- cron:") == 4


def test_regression_recheck_must_not_delete_scan_checkpoint():
    i = WF.index('if [ "${{ env.REQ_MODE }}" != "recheck" ]')
    assert "refs/heads/scan-checkpoint" in WF[i:i + 300]
    assert WF.count("refs/heads/scan-checkpoint") == 1


def test_daily_recheck_runs_in_scan_run_once_per_day_and_cannot_fail_the_batch():
    i = WF.index("Daily re-check of active parcels")
    block = WF[i:i + 1500]
    assert "continue-on-error: true" in block and "timeout-minutes: 60" in block
    assert '--stale-before "$(date -u +%F)"' in block
    assert "--parcel-list" in block
    assert block.index("Daily re-check") < WF.index("Enrich mirror tiks")
