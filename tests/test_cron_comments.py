"""Regression (#420): cron schedules run in UTC, and Israel switches between
UTC+3 and UTC+2 twice a year. A comment pairing a clock time with Israel or
local time ("03:00 UTC (06:00 Israel)") is therefore wrong for half the
year. No workflow comment may state a local clock time; prose about the DST
shift without a clock time is fine."""

import re
from pathlib import Path

_WF_DIR = Path(__file__).parent.parent / ".github" / "workflows"
WORKFLOWS = sorted([*_WF_DIR.glob("*.yml"), *_WF_DIR.glob("*.yaml")])
# A clock time next to a local-zone word, in either order: "06:00 Israel",
# "6:00 IDT", "09:00 local time", "06:00 (Israel)", "Israel time: 06:00",
# "local time 9:30", "Israel daylight-saving time: 06:00". The gap allows up
# to 40 characters, so longer zone phrasings are caught too (review on #500).
_CLOCK = r"\b\d{1,2}:\d{2}\b"
_ZONE = r"\b(?:Israel|IDT|IST|local)\b"
LOCAL_CLOCK = re.compile(
    rf"{_CLOCK}[^\n]{{0,40}}?{_ZONE}|{_ZONE}[^\n]{{0,40}}?{_CLOCK}", re.IGNORECASE
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


def test_pattern_catches_the_zone_before_the_clock():
    # Review on #500: the reversed order must be caught too.
    assert LOCAL_CLOCK.search(" Israel time: 06:00")
    assert LOCAL_CLOCK.search(" local time: 06:00")
    assert LOCAL_CLOCK.search(" batch 1 (IDT 06:00)")


def test_pattern_catches_a_long_zone_phrase():
    # Review on #500: more than 12 characters between zone word and clock.
    assert LOCAL_CLOCK.search(" Israel daylight-saving time: 06:00")
    assert LOCAL_CLOCK.search(" 06:00 in Israel daylight-saving time")
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
