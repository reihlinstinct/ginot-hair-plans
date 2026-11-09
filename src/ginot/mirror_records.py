"""Pure mirror record reconciliation and durable-enrichment selection."""

import datetime
import hashlib
import json

ENRICHED_FIELDS = ("publication_start", "publication_end_planned")

TERMINAL_STATUSES = {"הבקשה נסגרה", "הופק-הוצא היתר בניה", "הופק היתר מוארך", "נדחתה"}


def preserve_sample_bounds(records, old_records):
    """Keep the earliest first_seen / latest last_seen across re-ingests.

    The mirror resets first_seen when it re-writes a row (16 records moved
    later in one ingest, #794), which silently erases the earliest sighting.
    Carry the historical bounds forward like preserve_enriched_fields does."""
    old_by_tik = {r["tik_num"]: r for r in old_records}
    for tik, rec in records.items():
        old = old_by_tik.get(tik) or {}
        old_first, new_first = (
            old.get("mirror_first_seen"),
            rec.get("mirror_first_seen"),
        )
        if old_first and new_first:
            rec["mirror_first_seen"] = _iso_min(old_first, new_first)
        elif old_first:
            rec["mirror_first_seen"] = old_first
        old_last, new_last = old.get("mirror_last_seen"), rec.get("mirror_last_seen")
        if old_last and new_last:
            rec["mirror_last_seen"] = _iso_max(old_last, new_last)
        elif old_last:
            rec["mirror_last_seen"] = old_last


def _iso_min(a, b):
    """Earlier of two ISO timestamps; string order as fallback."""
    try:
        return min(a, b, key=datetime.datetime.fromisoformat)
    except (TypeError, ValueError):
        return min(a, b)


def _iso_max(a, b):
    try:
        return max(a, b, key=datetime.datetime.fromisoformat)
    except (TypeError, ValueError):
        return max(a, b)


def preserve_enriched_fields(records, old_records):
    """Carry nightly-enriched publication fields (issue #76) across re-ingests.

    map_record maps only mirror columns, so without this carry-over each
    ingest wipes the enrichment's output - and unchanged tiks are never
    re-enriched, because the diff selection is status-based. Empty-string
    markers (checked, no dates found) are preserved too, so the
    include-unenriched backfill does not refetch them."""
    old_by_tik = {r["tik_num"]: r for r in old_records}
    for tik, rec in records.items():
        old = old_by_tik.get(tik) or {}
        for key in ENRICHED_FIELDS:
            if key in old:
                rec[key] = old[key]


def diff_records(old_records, new_records):
    """Change detection between the previous ingest and this one.

    A tik counts as changed when its status or status_date moved; new
    and gone tiks are set differences. The output drives the nightly
    targeted publication-date enrichment (issue #76).
    """
    old_by_tik = {r["tik_num"]: r for r in old_records}
    new_by_tik = {r["tik_num"]: r for r in new_records}
    new_tiks = sorted(set(new_by_tik) - set(old_by_tik))
    gone_tiks = sorted(set(old_by_tik) - set(new_by_tik))
    changed = sorted(
        t
        for t in set(old_by_tik) & set(new_by_tik)
        if (old_by_tik[t].get("status"), old_by_tik[t].get("status_date"))
        != (new_by_tik[t].get("status"), new_by_tik[t].get("status_date"))
    )
    return {"new_tiks": new_tiks, "changed_tiks": changed, "gone_tiks": gone_tiks}


def content_marker(requests):
    """Content-derived ingest marker (issue #807): a hash of the canonical
    records list. A per-second timestamp changed the mirror payload and the
    queue file on every run, defeating the workflow's no-change short-circuit.
    The #799 contract is preserved: the marker still identifies exactly one
    committed ingest content, so a queue written against different mirror
    content is still detected by the mismatch; identical content legitimately
    shares a marker (the queue is equally valid for it)."""
    ordered = sorted(requests, key=lambda r: str(r.get("tik_num", "")))
    canonical = json.dumps(ordered, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def enrichment_queue(records, pending, previous_diff, current_diff):
    """Carry work across diff replacement, including stale-marker changes.

    Previous selections are conservatively retried: a publication marker
    cannot prove a changed case was enriched after its latest change.
    """
    selected = (
        pending
        | previous_diff
        | set(current_diff["new_tiks"] + current_diff["changed_tiks"])
    )
    return sorted(
        tik
        for tik in selected
        if tik in records and records[tik].get("status") not in TERMINAL_STATUSES
    )
