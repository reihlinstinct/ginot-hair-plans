#!/usr/bin/env python3
"""Decide whether a merged permit-feed data PR may start its successors (#565).

Usage: permit_router.py --repo OWNER/NAME --pr N

Runs from ``permit-feed-router.yml`` after a PR to ``main`` closes. It reads
only GitHub's own records through ``gh api``: the PR, the #566 provenance file
in the PR's git tree at its exact head SHA, the originating workflow run, the
PR reviews, commit comparisons and the PR's comments (for the dedup marker).
The PR title and body are never read. Nothing here writes, dispatches or
fetches municipal data: v1 is dry-run only and prints a decision.

Verdicts:
- ``route-scan-audit``: every check passed for a scan batch PR.
- ``skip``: not a routable data PR (other branch, fork, unmerged, no scan
  provenance) or already routed. Nothing to do.
- ``hold``: a real data PR without an approving review at its exact head.
- ``stop``: anything forged, mismatched, stale or unreadable. Exit 1.

Only fixed reason strings and numbers are printed, never names or bodies.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys

WORKFLOW_PATH = ".github/workflows/permit-feed.yml"
HEAD_PREFIX = "permit-feed/"
PROVENANCE_PATH = "data/permit_scan_provenance.json"
PROVENANCE_KEYS = {"note", "checkpoint_commit", "batch", "source_run"}
RUN_EVENTS = {"schedule", "workflow_dispatch", "push"}
MARKER = "<!-- permit-router: routed "
GH_TIMEOUT_SECONDS = 60
SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")


class RouterError(Exception):
    """The merged state could not be established; the job fails closed."""


def _sha(value):
    return isinstance(value, str) and SHA.match(value) is not None


def _int(value):
    return type(value) is int


def marker(number, head_sha, run_id):
    """The fixed dedup marker for one routed (PR, head, run)."""
    return f"{MARKER}{number} {head_sha} {run_id} -->"


def check_pr(repo, pr):
    """Return a skip reason, or None when this is a merged same-repo data PR."""
    if not isinstance(pr, dict) or not _int(pr.get("number")):
        raise RouterError("malformed pull request")
    head, base = pr.get("head"), pr.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise RouterError("malformed pull request")
    if not isinstance(head.get("ref"), str) or base.get("ref") != "main":
        return "not a main data PR"
    head_repo = head.get("repo")
    if not isinstance(head_repo, dict) or not isinstance(head_repo.get("full_name"), str):
        return "fork or deleted head repository"
    if head_repo["full_name"].lower() != repo.lower() or not head["ref"].startswith(HEAD_PREFIX):
        return "not a same-repo permit-feed PR"
    if pr.get("merged") is not True:
        return "not merged"
    if not _sha(head.get("sha")) or not _sha(base.get("sha")) or not _sha(pr.get("merge_commit_sha")):
        raise RouterError("malformed pull request SHAs")
    return None


def check_provenance(prov):
    """Return the source run ID from a #566 provenance record."""
    if not isinstance(prov, dict) or set(prov) != PROVENANCE_KEYS:
        raise RouterError("malformed provenance")
    batch = prov["batch"]
    if not _sha(prov["checkpoint_commit"]) or not isinstance(batch, dict) or set(batch) != {"offset", "limit"}:
        raise RouterError("malformed provenance")
    if not (_int(batch["offset"]) and _int(batch["limit"]) and batch["offset"] >= 0 and batch["limit"] > 0):
        raise RouterError("malformed provenance")
    run_id = prov["source_run"]
    if not isinstance(run_id, str) or not RUN_ID.match(run_id):
        raise RouterError("provenance has no source run")
    return int(run_id)


def check_run(repo, run, run_id):
    """The originating run must be this repo's permit-feed run on main, attempt 1, green."""
    if not isinstance(run, dict):
        raise RouterError("malformed run")
    repository, head_repository = run.get("repository"), run.get("head_repository")
    checks = [
        run.get("id") == run_id,
        run.get("path") == WORKFLOW_PATH,
        isinstance(repository, dict) and str(repository.get("full_name", "")).lower() == repo.lower(),
        isinstance(head_repository, dict) and str(head_repository.get("full_name", "")).lower() == repo.lower(),
        run.get("head_branch") == "main",
        run.get("event") in RUN_EVENTS,
        run.get("run_attempt") == 1,
        run.get("status") == "completed",
        run.get("conclusion") == "success",
        _sha(run.get("head_sha")),
    ]
    if not all(checks):
        raise RouterError("source run is not a green permit-feed run on main")
    return run["head_sha"]


def approved_at_head(pr, reviews):
    """True when someone other than the PR author approved the exact head SHA."""
    if not isinstance(reviews, list):
        raise RouterError("malformed reviews")
    author = (pr.get("user") or {}).get("login")
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("user"), dict):
            raise RouterError("malformed reviews")
        if (
            review.get("state") == "APPROVED"
            and review.get("commit_id") == pr["head"]["sha"]
            and review["user"].get("login") != author
        ):
            return True
    return False


def decide(repo, pr, read):
    """Return ``(verdict, reason)``. ``read`` answers the fixed questions below."""
    skip = check_pr(repo, pr)
    if skip:
        return "skip", skip
    if not read("ancestor", pr["merge_commit_sha"], "main"):
        raise RouterError("merge commit is not on main")
    prov = read("provenance", pr["head"]["sha"])
    if prov is None:
        return "skip", "no scan provenance"
    # The file persists on main after each merged batch, so a non-scan PR's tree
    # still carries the previous batch's record. Only a record this PR changed binds it.
    if prov == read("provenance", pr["base"]["sha"]):
        return "skip", "provenance not changed by this PR"
    run_id = check_provenance(prov)
    run_head = check_run(repo, read("run", run_id), run_id)
    if not read("ancestor", run_head, pr["base"]["sha"]):
        raise RouterError("source run is not behind the PR base")
    if marker(pr["number"], pr["head"]["sha"], run_id) in read("markers", pr["number"]):
        return "skip", "already routed"
    if not approved_at_head(pr, read("reviews", pr["number"])):
        return "hold", "no approval at the exact head"
    return "route-scan-audit", "verified"


def _gh(path):
    try:
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                           check=False, timeout=GH_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RouterError("gh api unavailable") from exc
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError as exc:
        raise RouterError("gh api returned non-JSON") from exc


def github_reader(repo, gh=_gh):
    """Answer ``decide``'s questions from GitHub REST, failing closed."""
    def need(value):
        if value is None:
            raise RouterError("GitHub record unreadable")
        return value

    def read(kind, *args):
        if kind == "ancestor":
            cmp = need(gh(f"repos/{repo}/compare/{args[0]}...{args[1]}"))
            return isinstance(cmp, dict) and cmp.get("status") in ("ahead", "identical")
        if kind == "provenance":
            meta = gh(f"repos/{repo}/contents/{PROVENANCE_PATH}?ref={args[0]}")
            if meta is None:
                return None  # 404: a PR without the #566 binding
            if not isinstance(meta, dict) or meta.get("encoding") != "base64":
                raise RouterError("malformed provenance file")
            try:
                return json.loads(base64.b64decode(meta.get("content", ""), validate=False))
            except ValueError as exc:
                raise RouterError("malformed provenance file") from exc
        if kind == "run":
            return need(gh(f"repos/{repo}/actions/runs/{args[0]}"))
        if kind == "reviews":
            return need(gh(f"repos/{repo}/pulls/{args[0]}/reviews?per_page=100"))
        if kind == "markers":
            comments = need(gh(f"repos/{repo}/issues/{args[0]}/comments?per_page=100"))
            if not isinstance(comments, list):
                raise RouterError("malformed comments")
            return "\n".join(c.get("body", "") for c in comments if isinstance(c, dict)
                             and isinstance(c.get("body"), str))
        raise RouterError("unknown question")
    return read


def main(argv=None, gh=_gh):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    args = ap.parse_args(argv)
    try:
        pr = gh(f"repos/{args.repo}/pulls/{args.pr}")
        if pr is None:
            raise RouterError("pull request unreadable")
        verdict, reason = decide(args.repo, pr, github_reader(args.repo, gh))
    except RouterError as exc:
        verdict, reason = "stop", str(exc)
    line = f"verdict={verdict} reason={reason} pr={args.pr} dispatch=off"
    print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"verdict={verdict}\n")
    return 1 if verdict == "stop" else 0


if __name__ == "__main__":
    sys.exit(main())
