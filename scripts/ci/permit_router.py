#!/usr/bin/env python3
"""Decide whether a merged permit-feed data PR may start its successors (#565).

Usage: permit_router.py --repo OWNER/NAME --pr N

Runs from ``permit-feed-router.yml`` after a PR to ``main`` closes. It reads
only GitHub's own records through ``gh api``: the PR, its changed-file list
(generated data paths only), the #566 provenance file
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
import fnmatch
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
PER_PAGE = 100
# Bound on pages per list endpoint: beyond it the router fails closed
# rather than trusting an unbounded exchange (issue #708).
MAX_PAGES = 5
SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
# The generated paths permit-feed.yml stages into a data PR (its `git add`).
# The workflow YAML is read from main after the merge, so a "data" PR that also
# touches code or workflows must never be routed as data.
DATA_PREFIXES = ("data/",)
DATA_FILES = {
    "docs/data.json",
    "docs/index.json",
    "docs/index.html",  # generated permit-coverage counts (#870)
    "docs/permits.html",
    "docs/permits-default.html",
    "docs/permit-ids.json",
    "docs/permit-points.json",
}
DATA_GLOB = "docs/badge/parcel-*.json"

# Every review state GitHub emits today. States outside this set are not
# skipped silently: they stop the router red (see approved_at_head).
KNOWN_REVIEW_STATES = {
    "APPROVED",
    "CHANGES_REQUESTED",
    "COMMENTED",
    "DISMISSED",
    "PENDING",
}


class RouterError(Exception):
    """The merged state could not be established; the job fails closed."""


# Section: Routing decision


def decide(repo, pr, read):
    """Return ``(verdict, reason)``. ``read`` answers the fixed questions below."""
    skip = check_pr(repo, pr)
    if skip:
        return "skip", skip
    if not read("ancestor", pr["merge_commit_sha"], "main"):
        raise RouterError("merge commit is not on main")
    check_files(pr, read("files", pr["number"]))
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
    if not isinstance(head_repo, dict) or not isinstance(
        head_repo.get("full_name"), str
    ):
        return "fork or deleted head repository"
    if head_repo["full_name"].lower() != repo.lower() or not head["ref"].startswith(
        HEAD_PREFIX
    ):
        return "not a same-repo permit-feed PR"
    if pr.get("merged") is not True:
        return "not merged"
    if (
        not _sha(head.get("sha"))
        or not _sha(base.get("sha"))
        or not _sha(pr.get("merge_commit_sha"))
    ):
        raise RouterError("malformed pull request SHAs")
    return None


def _sha(value):
    return isinstance(value, str) and SHA.match(value) is not None


def _int(value):
    return type(value) is int


def check_files(pr, files):
    """Stop unless the PR changed only generated data paths, with a complete list."""
    if (
        not isinstance(files, list)
        or not files
        or len(files) != pr.get("changed_files")
    ):
        raise RouterError("changed files incomplete or malformed")
    for entry in files:
        if not isinstance(entry, dict):
            raise RouterError("changed files incomplete or malformed")
        paths = [entry.get("filename")]
        if "previous_filename" in entry:
            paths.append(entry["previous_filename"])
        if not all(_data_path(path) for path in paths):
            raise RouterError("PR changes paths outside the generated data")


def _data_path(path):
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        return False
    if any(part in ("", ".", "..") for part in path.split("/")):
        return False
    if path.startswith(DATA_PREFIXES) or path in DATA_FILES:
        return True
    return fnmatch.fnmatchcase(path, DATA_GLOB) and path.count("/") == DATA_GLOB.count(
        "/"
    )


def check_provenance(prov):
    """Return the source run ID from a #566 provenance record."""
    if not isinstance(prov, dict) or set(prov) != PROVENANCE_KEYS:
        raise RouterError("malformed provenance")
    batch = prov["batch"]
    if (
        not _sha(prov["checkpoint_commit"])
        or not isinstance(batch, dict)
        or set(batch) != {"offset", "limit"}
    ):
        raise RouterError("malformed provenance")
    if not (
        _int(batch["offset"])
        and _int(batch["limit"])
        and batch["offset"] >= 0
        and batch["limit"] > 0
    ):
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
        isinstance(repository, dict)
        and str(repository.get("full_name", "")).lower() == repo.lower(),
        isinstance(head_repository, dict)
        and str(head_repository.get("full_name", "")).lower() == repo.lower(),
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


def marker(number, head_sha, run_id):
    """The fixed dedup marker for one routed (PR, head, run)."""
    return f"{MARKER}{number} {head_sha} {run_id} -->"


def approved_at_head(pr, reviews):
    """True when someone other than the PR author approved the exact head SHA."""
    if not isinstance(reviews, list):
        raise RouterError("malformed reviews")
    author = (pr.get("user") or {}).get("login")
    latest = {}  # reviewer -> last decisive review; the API lists reviews oldest first
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("user"), dict):
            raise RouterError("malformed reviews")
        login = review["user"].get("login")
        # A decisive review without a verifiable non-empty login must fail
        # closed; it must never count as an approval by "someone else".
        if not isinstance(login, str) or not login:
            raise RouterError("malformed reviews")
        # An unverifiable state must fail closed too: skipping the record
        # would let an earlier exact-head APPROVED stand in for it.
        state = review.get("state")
        if not isinstance(state, str) or not state:
            raise RouterError("malformed reviews")
        # A well-formed state outside the known set fails closed as well
        # (#755): if GitHub ever adds a decisive-looking state, the router
        # must surface it loudly instead of silently skipping the review.
        if state not in KNOWN_REVIEW_STATES:
            # Value-free like every other RouterError: the state string is
            # API-supplied data and the reason is printed into logs and
            # GITHUB_OUTPUT.
            raise RouterError("unknown review state")
        if state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED") and login != author:
            latest[login] = review
    states = [(r.get("state"), r.get("commit_id")) for r in latest.values()]
    if any(state == "CHANGES_REQUESTED" for state, _ in states):
        return False
    return ("APPROVED", pr["head"]["sha"]) in states


# Section: GitHub transport


class GitHubHTTPError(RouterError):
    """GitHub returned an HTTP failure, with its status preserved."""

    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub HTTP {status}")


def _gh(path):
    try:
        r = subprocess.run(
            ["gh", "api", "--include", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RouterError("gh api unavailable") from exc
    header, separator, body = r.stdout.replace("\r\n", "\n").partition("\n\n")
    status = re.match(r"HTTP/\S+ ([0-9]{3})(?: |$)", header)
    if not separator or status is None:
        raise RouterError("GitHub HTTP status unreadable")
    code = int(status.group(1))
    if not 200 <= code < 300:
        raise GitHubHTTPError(code)
    if r.returncode != 0:
        raise RouterError("gh api failed")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise RouterError("gh api returned non-JSON") from exc


def github_reader(repo, gh=_gh):
    """Answer ``decide``'s questions from GitHub REST, failing closed."""

    def need(value):
        if value is None:
            raise RouterError("GitHub record unreadable")
        return value

    def collect(path):
        # Bounded pagination (#708): follow pages until a short one - a full
        # page may hide a later review, file or dedup marker, and an exact
        # multiple of the page size ends on an empty terminal page. The
        # budget buys MAX_PAGES full pages plus one terminal probe, so
        # exactly-MAX_PAGES-full-pages endpoints validate instead of being
        # rejected unprobed. Fail closed on a malformed page or when the
        # budget runs out.
        items = []
        for page in range(1, MAX_PAGES + 2):
            chunk = need(gh(f"{path}&page={page}"))
            if not isinstance(chunk, list):
                raise RouterError("list response incomplete or malformed")
            items.extend(chunk)
            if len(chunk) < PER_PAGE:
                return items
        raise RouterError("list response exceeds the pagination budget")

    def read(kind, *args):
        if kind == "ancestor":
            cmp = need(gh(f"repos/{repo}/compare/{args[0]}...{args[1]}"))
            return isinstance(cmp, dict) and cmp.get("status") in ("ahead", "identical")
        if kind == "provenance":
            ref = args[0]
            if not _sha(ref):
                raise RouterError("malformed provenance ref")
            try:
                meta = gh(f"repos/{repo}/contents/{PROVENANCE_PATH}?ref={ref}")
            except GitHubHTTPError as exc:
                if exc.status != 404:
                    raise
                # A contents 404 can also mean the ref is unavailable. Verify it
                # independently before treating only the file as absent.
                commit = need(gh(f"repos/{repo}/git/commits/{ref}"))
                if not isinstance(commit, dict) or commit.get("sha") != ref:
                    raise RouterError("provenance ref unreadable")
                return None
            if not isinstance(meta, dict) or meta.get("encoding") != "base64":
                raise RouterError("malformed provenance file")
            try:
                return json.loads(
                    base64.b64decode(meta.get("content", ""), validate=False)
                )
            except ValueError as exc:
                raise RouterError("malformed provenance file") from exc
        if kind == "run":
            return need(gh(f"repos/{repo}/actions/runs/{args[0]}"))
        if kind == "reviews":
            return collect(f"repos/{repo}/pulls/{args[0]}/reviews?per_page={PER_PAGE}")
        if kind == "files":
            return collect(f"repos/{repo}/pulls/{args[0]}/files?per_page={PER_PAGE}")
        if kind == "markers":
            comments = collect(
                f"repos/{repo}/issues/{args[0]}/comments?per_page={PER_PAGE}"
            )
            bodies = []
            for c in comments:
                # A malformed record is dropped silently no longer: error out
                # before the dedup marker scan instead of trusting a partial
                # comment set.
                if not isinstance(c, dict) or not isinstance(c.get("body"), str):
                    raise RouterError("malformed comment record")
                bodies.append(c["body"])
            return "\n".join(bodies)
        raise RouterError("unknown question")

    return read


# Section: Command line


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
