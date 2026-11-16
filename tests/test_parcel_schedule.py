"""Bounded serial backfill schedule, without dispatching any network work."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_backfill_four_evenly_spaced_windows_preserve_safety_limits():
    workflow = (ROOT / ".github/workflows/permit-feed.yml").read_text()
    hours = [int(x) for x in re.findall(r'cron: "0 (\d+) \* \* \*"', workflow)]
    assert hours == [3, 9, 15, 21]
    assert all((hours[(i + 1) % 4] - hours[i]) % 24 == 6 for i in range(4))
    assert "group: permit-feed" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "L=280" in workflow
    assert "BACKFILL_COMPLETE=true" in workflow
    assert "PACE_SECONDS = 3.0" in (ROOT / "scripts/vpn/permit_feed.py").read_text()
