"""Regression (#420): cron schedules run in UTC, and Israel switches between
UTC+3 and UTC+2 twice a year. A local-time parenthetical next to a cron line
is therefore wrong for half the year. Workflow cron comments must state UTC
only."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
CRON = re.compile(r"^\s*-\s*cron:")
LOCAL_TIME = re.compile(r"\bIsrael\b|\bIDT\b|\bIST\b|\blocal time\b", re.IGNORECASE)


def _cron_comment_lines():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CRON.match(line) and "#" in line:
                yield path.name, lineno, line.split("#", 1)[1]


def test_workflows_have_cron_lines():
    assert list(_cron_comment_lines()), "expected at least one commented cron line"


def test_cron_comments_state_no_local_time():
    offenders = [
        f"{name}:{lineno}: {comment.strip()}"
        for name, lineno, comment in _cron_comment_lines()
        if LOCAL_TIME.search(comment)
    ]
    assert not offenders, "cron comments must state UTC only:\n" + "\n".join(offenders)
