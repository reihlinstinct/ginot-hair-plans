"""CI validation for data/deadline_overrides.json (#1082).

A malformed override must fail loudly here instead of being silently
ignored by refresh.merge_land_status.
"""

import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / "data" / "deadline_overrides.json"
# A verified window must be plausible: deposit-notice objection windows are
# weeks, not days and not years.
MIN_WINDOW_DAYS = 14
MAX_WINDOW_DAYS = 120


def _iso(value):
    return datetime.date.fromisoformat(value)  # raises on invalid/missing


def test_overrides_file_is_wellformed():
    data = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    plans = data.get("plans")
    assert isinstance(plans, dict) and plans, "overrides must hold a plans map"
    for pl_number, entry in plans.items():
        assert set(entry) >= {"deadline", "publication_date", "source"}, pl_number
        deadline = _iso(entry["deadline"])
        anchor = _iso(entry["publication_date"])
        assert entry["source"].strip(), pl_number
        sources = entry.get("sources")
        if sources is not None:
            assert isinstance(sources, list) and all(s.strip() for s in sources), (
                pl_number
            )
        window = (deadline - anchor).days
        assert MIN_WINDOW_DAYS <= window <= MAX_WINDOW_DAYS, (
            f"{pl_number}: deadline {window}d after its publication anchor"
        )


def test_overrides_file_ends_with_newline():
    assert OVERRIDES.read_bytes().endswith(b"\n")
