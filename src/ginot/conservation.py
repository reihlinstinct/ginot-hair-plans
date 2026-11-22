"""Conservation committee cases shown on their own, never attached to a plan or permit.

A case is a card from a municipal conservation (shimur) committee agenda. It carries a
plan number as printed on that card, which is not necessarily a Mavat plan, and it is not
a permit request. The data file keeps each case apart so nothing is linked by guesswork.
"""

import datetime
import html
import json
import re
from pathlib import Path

REQUIRED = (
    "case_id",
    "address",
    "plan_ref",
    "gush",
    "helka",
    "committee",
    "meeting_date",
    "source_url",
    "review_path",
)
_DIGITS = re.compile(r"^\d{1,8}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REVIEW = re.compile(r"^reviews/[\w\-./]+\.html$")


def _real_date(value: str) -> bool:
    if not _DATE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def load(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("cases", [])


def validate(cases: list[dict]) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems, seen = [], set()
    for i, c in enumerate(cases):
        where = f"case {i}"
        if not isinstance(c, dict) or set(c) != set(REQUIRED):
            problems.append(f"{where}: fields must be exactly {REQUIRED}")
            continue
        for k in ("case_id", "plan_ref", "gush", "helka"):
            if not _DIGITS.match(str(c[k])):
                problems.append(f"{where}: {k} must be digits")
        if not _real_date(str(c["meeting_date"])):
            problems.append(f"{where}: meeting_date must be a real YYYY-MM-DD date")
        if not str(c["source_url"]).startswith("https://"):
            problems.append(f"{where}: source_url must be https")
        if not _REVIEW.match(str(c["review_path"])) or ".." in str(c["review_path"]):
            problems.append(f"{where}: review_path must be a docs/reviews html page")
        if c["case_id"] in seen:
            problems.append(f"{where}: duplicate case_id {c['case_id']}")
        seen.add(c["case_id"])
    return problems


def render_section(cases: list[dict], t, pre: str) -> str:
    """Collapsed section; empty string when there is nothing to show."""
    if not cases or validate(cases):
        return ""
    e = html.escape
    items = []
    for c in cases:
        y, m, d = c["meeting_date"].split("-")
        items.append(
            "<li>"
            f"<strong>{e(t('conservation.case'))} {e(c['case_id'])}</strong> "
            f'<span dir="auto">{e(c["address"])}</span><br>'
            f'{e(t("conservation.plan_ref"))}: <span dir="ltr">{e(c["plan_ref"])}</span>'
            f' &middot; {e(t("conservation.parcel"))}: <span dir="ltr">'
            f"{e(c['gush'])}/{e(c['helka'])}</span>"
            f' &middot; {e(t("conservation.meeting"))} <span dir="ltr">'
            f"{e(c['committee'])}, {d}.{m}.{y}</span><br>"
            f'<a href="{e(pre + c["review_path"], quote=True)}">'
            f"{e(t('conservation.review'))}</a>"
            f' &middot; <a href="{e(c["source_url"], quote=True)}" rel="noopener">'
            f"{e(t('conservation.source'))}</a></li>"
        )
    return (
        '<details id="conservation-panel" class="changes-panel">'
        f"<summary><h2>{e(t('conservation.h'))} ({len(cases)})</h2></summary>"
        f"<p>{e(t('conservation.note'))}</p>"
        f'<ul id="conservation-list">{"".join(items)}</ul></details>'
    )
