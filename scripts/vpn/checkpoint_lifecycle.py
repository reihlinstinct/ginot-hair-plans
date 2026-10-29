"""Bind the scan checkpoint to its data PR's lifecycle (issue #566).

A complete scan leaves a full checkpoint on the ``scan-checkpoint`` branch.
If the data PR built from it is closed without merging, ``main``'s batch
cursor does not move, so the next run would resume that checkpoint and put
the rejected rows into a replacement PR. The open-only #564 guard cannot see
a closed PR.

Binding: a checkpointed scan writes ``data/permit_scan_provenance.json`` with
the commit SHA of its last confirmed checkpoint push. The publish step's
``git add data/`` puts that file in the data PR's head commit, so the binding
is read from the PR's git tree at its exact head SHA, never from the PR title
or body.

Gate (before any municipal request): read the checkpoint head commit, every
same-repo ``permit-feed/`` PR updated since that commit, and each PR's
provenance file at its head SHA, then :func:`decide`. Any unreadable or
error-shaped GitHub response raises :class:`LifecycleError`; callers stop
(fail closed). Nothing here writes, deletes or dispatches anything.
"""

import base64
import json

PROVENANCE_NAME = "permit_scan_provenance.json"
PROVENANCE_PATH = f"data/{PROVENANCE_NAME}"
HEAD_PREFIX = "permit-feed/"
PER_PAGE = 100
MAX_PAGES = 20

# Verdicts that let the scan continue; every other verdict stops the run.
PROCEED = frozenset({"none", "unbound", "consumed", "stale"})


class LifecycleError(Exception):
    """The checkpoint lifecycle could not be established; stop (fail closed)."""


def provenance(checkpoint_commit, offset, limit, run_id=None):
    """The provenance record a checkpointed scan commits with its feed."""
    return {
        "note": "scan checkpoint binding (issue #566); written by permit_feed.py",
        "checkpoint_commit": checkpoint_commit,
        "batch": {"offset": offset, "limit": limit},
        "source_run": run_id or None,
    }


def _batch_key(batch):
    if not isinstance(batch, dict):
        return None
    offset, limit = batch.get("offset"), batch.get("limit")
    if type(offset) is not int or type(limit) is not int:
        return None
    return offset, limit


def decide(cp_commit, cp_batch, main_batch, prs):
    """Return ``(verdict, pr_numbers)`` for the checkpoint at ``cp_commit``.

    ``prs`` are trusted candidates (same repo, ``permit-feed/`` head), each a
    dict with ``number``, ``state`` (``open``/``closed``), ``merged`` (bool)
    and ``provenance`` (dict or None). ``main_batch`` is the ``batch`` cursor
    of ``main``'s feed (None when it has none).
    """
    if not cp_commit:
        return "none", []
    cp_key = _batch_key(cp_batch)
    if cp_key is None:
        raise LifecycleError("checkpoint has no valid batch offset/limit")
    bound = [
        p
        for p in prs
        if isinstance(p.get("provenance"), dict)
        and p["provenance"].get("checkpoint_commit") == cp_commit
    ]
    if not bound:
        return "unbound", []
    numbers = sorted(p["number"] for p in bound)
    bad = [
        p["number"] for p in bound if _batch_key(p["provenance"].get("batch")) != cp_key
    ]
    if bad:
        return "mismatch", sorted(bad)
    # An open bound PR blocks even when another bound PR merged: the batch
    # still has unreviewed data in flight.
    if any(p["state"] == "open" for p in bound):
        return "pending", numbers
    if any(p["merged"] for p in bound):
        return "consumed", numbers
    # Every bound PR is closed unmerged. If main's cursor already reached this
    # batch (a re-authored replacement landed it) or moved past it, the
    # checkpoint can no longer be resumed: stale, not rejected.
    main_key = _batch_key(main_batch)
    if main_key is not None and main_key[0] >= cp_key[0]:
        return "stale", numbers
    return "rejected", numbers


def _require(cond, what):
    if not cond:
        raise LifecycleError(what)


def checkpoint_head(gh, token, slug, branch):
    """``(sha, date)`` of the checkpoint branch head, or ``(None, None)``."""
    r = gh("GET", f"/repos/{slug}/branches/{branch}", token)
    if isinstance(r, dict) and r.get("message") == "Branch not found":
        return None, None
    try:
        commit = r["commit"]
        sha, date = commit["sha"], commit["commit"]["committer"]["date"]
    except (KeyError, TypeError) as exc:
        raise LifecycleError(
            f"unreadable checkpoint branch response ({exc!r})"
        ) from None
    _require(isinstance(sha, str) and len(sha) == 40, "bad checkpoint head sha")
    _require(isinstance(date, str) and date, "bad checkpoint head date")
    return sha, date


def read_checkpoint(gh, token, slug, sha):
    """The checkpoint payload at commit ``sha``, or None when that commit has
    no ``data/permit_requests.json``. Any other unreadable answer (error body,
    an empty ``content`` such as a file over the contents API's 1 MB limit,
    bad base64 or JSON) raises: an unread checkpoint is not an absent one."""
    r = gh("GET", f"/repos/{slug}/contents/data/permit_requests.json?ref={sha}", token)
    if isinstance(r, dict) and r.get("message") == "Not Found":
        return None
    try:
        content = r["content"]
        _require(isinstance(content, str) and content, "empty checkpoint content")
        return json.loads(base64.b64decode(content))
    except (KeyError, TypeError, ValueError) as exc:
        raise LifecycleError(f"unreadable checkpoint at {sha[:7]} ({exc!r})") from None


def _pr_provenance(gh, token, slug, head_sha):
    r = gh("GET", f"/repos/{slug}/contents/{PROVENANCE_PATH}?ref={head_sha}", token)
    if isinstance(r, dict) and r.get("message") == "Not Found":
        return None  # PR predates #566: unbound, as before
    try:
        data = json.loads(base64.b64decode(r["content"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise LifecycleError(
            f"unreadable provenance at {head_sha[:7]} ({exc!r})"
        ) from None
    _require(isinstance(data, dict), f"provenance at {head_sha[:7]} is not an object")
    return data


def candidate_prs(gh, token, slug, since):
    """Same-repo ``permit-feed/`` PRs created at or after ``since``, with the
    provenance read at each PR's exact head SHA."""
    out = []
    for page in range(1, MAX_PAGES + 1):
        items = gh(
            "GET",
            f"/repos/{slug}/pulls?state=all&sort=updated&direction=desc"
            f"&per_page={PER_PAGE}&page={page}",
            token,
        )
        _require(isinstance(items, list), f"PR page {page} is not a list")
        for pr in items:
            try:
                number, state = pr["number"], pr["state"]
                created, updated = pr["created_at"], pr["updated_at"]
                head = pr["head"]
                ref, sha, repo = head["ref"], head["sha"], head["repo"]
                merged = pr["merged_at"] is not None
            except (KeyError, TypeError) as exc:
                raise LifecycleError(f"malformed PR entry ({exc!r})") from None
            _require(
                type(number) is int
                and state in ("open", "closed")
                and isinstance(created, str)
                and isinstance(updated, str)
                and isinstance(ref, str)
                and isinstance(sha, str),
                "malformed PR entry",
            )
            if not (
                isinstance(repo, dict)
                and isinstance(repo.get("full_name"), str)
                and repo["full_name"].lower() == slug.lower()
                and ref.startswith(HEAD_PREFIX)
                and created >= since
            ):
                continue  # forks, deleted forks, other prefixes, older PRs
            out.append(
                {
                    "number": number,
                    "state": state,
                    "merged": merged,
                    "provenance": _pr_provenance(gh, token, slug, sha),
                }
            )
        # Sorted by update time: once a page reaches PRs last updated before
        # the checkpoint commit, no later page can hold a PR created after it.
        if len(items) < PER_PAGE or items[-1]["updated_at"] < since:
            return out
    raise LifecycleError(f"more than {MAX_PAGES} PR pages")
