"""Planner tracking model: per-plan review state, stored in data/plan_status.json.

States: new (default on first appearance), reviewed, objection_filed,
no_objection_needed, urgent. All state changes are human-made (the planner's),
except: missing plans default to 'new', and an *advisory* urgent flag is
computed when a plan in an undecided state (new/reviewed) has a derived
objection deadline within URGENT_WITHIN_DAYS. Nothing is ever auto-filed;
this model is bookkeeping for a human reviewer only.
"""
import datetime
import json
import os

STATES = ("new", "reviewed", "objection_filed", "no_objection_needed", "urgent")
UNDECIDED = ("new", "reviewed")
URGENT_WITHIN_DAYS = 30


def load(path: str) -> dict:
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return {}


def save(states: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(states, fh, ensure_ascii=False, indent=1, sort_keys=True)


def _days_to(date_iso: str, today: datetime.date) -> int | None:
    if not date_iso:
        return None
    try:
        return (datetime.date.fromisoformat(date_iso) - today).days
    except ValueError:
        return None


def merge(rows: list[dict], states: dict, today: datetime.date | None = None) -> tuple[list[dict], dict]:
    """Attach tracking fields to rows; add defaults for plans never seen.
    Returns (rows, states) - states may have gained defaults (caller saves)."""
    today = today or datetime.date.today()
    changed = False
    for r in rows:
        num = r["pl_number"]
        st = states.get(num)
        if st is None:
            st = {"state": "new", "updated": today.isoformat(), "note": ""}
            states[num] = st
            changed = True
        days = _days_to(r.get("objection_deadline_derived_60d_from_publication", ""), today)
        advisory_urgent = (st["state"] in UNDECIDED and days is not None
                           and 0 <= days <= URGENT_WITHIN_DAYS)
        r["tracking_state"] = "urgent" if advisory_urgent else st["state"]
        r["tracking_urgent_advisory"] = advisory_urgent
        r["tracking_note"] = st.get("note", "")
        r["tracking_updated"] = st.get("updated", "")
    return rows, changed


def set_state(states: dict, pl_number: str, state: str, note: str = "") -> dict:
    assert state in STATES, state
    states[pl_number] = {"state": state, "updated": datetime.date.today().isoformat(), "note": note}
    return states
