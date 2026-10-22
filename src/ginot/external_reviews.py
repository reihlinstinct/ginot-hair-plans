"""External AI reviews: append-only store, validation and rendering (issue: external reviews).

Entries come from human-approved submissions in the private inbox. The file is
append-only: existing entries must never change or disappear (see check_append_only).
Submitted text is untrusted: it is validated here and always HTML-escaped on render.
"""
import html
import json
import re
from pathlib import Path

REQUIRED = ("id", "pl_number", "agent_name", "text", "submitted", "approved")
MAX_TEXT = 1500
BAD_TEXT = re.compile(r"https?:|www\.|<|>|\]\(|@\w+\.\w+|data:|javascript:", re.IGNORECASE)
NAME_OK = re.compile(r"^[\w .\-]{1,40}$")
DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("entries", [])


def validate_entries(entries: list[dict]) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems, seen = [], set()
    for i, e in enumerate(entries):
        where = f"entry {i}"
        if not isinstance(e, dict) or set(e) != set(REQUIRED):
            problems.append(f"{where}: fields must be exactly {REQUIRED}")
            continue
        if e["id"] in seen:
            problems.append(f"{where}: duplicate id {e['id']}")
        seen.add(e["id"])
        if not isinstance(e["text"], str) or not 40 <= len(e["text"]) <= MAX_TEXT or BAD_TEXT.search(e["text"]):
            problems.append(f"{where}: text must be 40-{MAX_TEXT} chars without links or HTML")
        if not NAME_OK.match(str(e["agent_name"])):
            problems.append(f"{where}: bad agent_name")
        for k in ("submitted", "approved"):
            if not DATE_OK.match(str(e[k])):
                problems.append(f"{where}: {k} must be YYYY-MM-DD")
    return problems


def check_append_only(base: list[dict], head: list[dict]) -> list[str]:
    """Head must start with base unchanged; only additions allowed."""
    problems = []
    if len(head) < len(base):
        problems.append(f"{len(base) - len(head)} existing entr(ies) removed")
    for i, old in enumerate(base[: len(head)]):
        if head[i] != old:
            problems.append(f"existing entry {old.get('id')} was modified or reordered")
    return problems


def render_section(entries: list[dict], pl_number: str) -> str:
    """Collapsed, clearly labelled section; empty string when there is nothing to show."""
    mine = [e for e in entries if e["pl_number"] == pl_number]
    if not mine:
        return ""
    items = "".join(
        f"<li><p>{html.escape(e['text'])}</p><p class='ext-meta'>הוגש על ידי: "
        f"<span dir='ltr'>{html.escape(e['agent_name'])}</span> (לא מאומת) · "
        f"<span dir='ltr'>{html.escape(e['submitted'])}</span></p></li>" for e in mine)
    return ("<details class='external-reviews'><summary>סקירות AI חיצוניות (לא מאומתות, "
            f"{len(mine)})</summary><p class='ext-note'>סקירות שהוגשו על ידי סוכני AI חיצוניים ואושרו "
            "לפרסום. אינן של בעלי האתר, אינן מסמך רשמי ואינן נבדקות לנכונות.</p>"
            f"<ul>{items}</ul></details>")
