"""Jerusalem-local "today" (issue #331).

date.today() on a GitHub-hosted runner is UTC. The site defines "today" in
Asia/Jerusalem (see page.py's client-side _todayIL()), so any server-side use
of date.today() is off by one between 21:00 and 24:00 UTC in summer (22:00 to
24:00 in winter) - the window where Israel has already rolled to the next day.
"""

import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Jerusalem")


def today_il() -> datetime.date:
    """Today's date in Asia/Jerusalem, matching the page's client-side clock."""
    return datetime.datetime.now(_TZ).date()
