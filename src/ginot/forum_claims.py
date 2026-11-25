"""Attributed forum-summary deadline claims (display only).

Shared by the refresh and by page.render_site, so the committed docs/ render
(and the docs-fresh gate, which re-renders from committed inputs) show the same
claims whether or not a row snapshot already carries them.
"""

import json

_FORUM_CLAIM_FIELDS = (
    "forum_deadline_claim",
    "forum_deadline_claim_forum_date",
    "forum_deadline_claim_source",
)


def merge_forum_deadline_claims(rows, path="data/forum_deadline_claims.json"):
    """Attach attributed forum-summary deadlines (data/forum_deadline_claims.json).

    A claim is display-only context: it never changes the verified or derived
    deadline fields, so sorting and urgency stay on the computed deadline. It is
    attached only while it differs from the deadline the site would show.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            claims = json.load(fh).get("plans", {})
    except (FileNotFoundError, json.JSONDecodeError):
        claims = {}
    for r in rows:
        # Always start clean so a stale claim (carried in a snapshot row) can
        # never survive a removed entry or a computed date that now matches.
        for k in _FORUM_CLAIM_FIELDS:
            r.pop(k, None)
        c = claims.get(r.get("pl_number") or "")
        if not c or not c.get("deadline"):
            continue
        shown = r.get("objection_deadline_verified") or r.get(
            "objection_deadline_derived_2m_from_publication"
        )
        if shown == c["deadline"]:
            continue
        r["forum_deadline_claim"] = c["deadline"]
        r["forum_deadline_claim_forum_date"] = c.get("forum_date", "")
        r["forum_deadline_claim_source"] = c.get("source", "")
    return rows
