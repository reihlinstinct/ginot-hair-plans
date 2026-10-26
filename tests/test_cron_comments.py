"""Regression (#420): cron schedules run in UTC, and Israel switches between
UTC+3 and UTC+2 twice a year. A comment pairing a clock time with Israel or
local time ("03:00 UTC (06:00 Israel)") is therefore wrong for half the
year. No workflow comment may state a local clock time; prose about the DST
shift without a clock time is fine."""

import re
from pathlib import Path

_WF_DIR = Path(__file__).parent.parent / ".github" / "workflows"
WORKFLOWS = sorted([*_WF_DIR.glob("*.yml"), *_WF_DIR.glob("*.yaml")])
# A clock time followed closely by a local-zone word: "06:00 Israel",
# "6:00 IDT", "09:00 local time", "06:00 (Israel)".
LOCAL_CLOCK = re.compile(
    r"\b\d{1,2}:\d{2}\b[^\n]{0,12}?\b(Israel|IDT|IST|local)\b", re.IGNORECASE
)


def _comments():
    for path in WORKFLOWS:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "#" in line:
                yield path.name, lineno, line.split("#", 1)[1]


def test_pattern_catches_the_original_comment():
    assert LOCAL_CLOCK.search(" daily backfill batch 1, 03:00 UTC (06:00 Israel)")
    assert LOCAL_CLOCK.search(" runs at 9:30 local time")
    assert not LOCAL_CLOCK.search(" Israel local time shifts by an hour at DST")
    assert not LOCAL_CLOCK.search(" nightly 03:20 UTC mirror-diff")


def test_workflows_have_comments():
    assert list(_comments())


def test_no_workflow_comment_states_a_local_clock_time():
    offenders = [
        f"{name}:{lineno}: {comment.strip()}"
        for name, lineno, comment in _comments()
        if LOCAL_CLOCK.search(comment)
    ]
    assert not offenders, "state UTC only in workflow comments:\n" + "\n".join(
        offenders
    )
