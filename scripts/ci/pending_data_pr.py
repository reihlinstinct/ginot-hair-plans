#!/usr/bin/env python3
"""Report whether a same-repo data PR with a given branch prefix awaits review.

Usage: pending_data_pr.py --repo OWNER/NAME --prefix weekly-refresh/ [--base BRANCH]

Scheduled data workflows call this before any network fetch, VPN or tunnel so a
run never stacks a second data PR while one is still waiting for independent
review (refs #564).

Rules:
- Lists open PRs page by page (``per_page=100&page=N``) until a short page.
  Draft PRs are open PRs, so they count as pending too.
- By default PRs targeting ANY base branch count: a data PR opened against a
  non-default branch is still unreviewed data. ``--base`` narrows the check to
  one base branch only when a caller explicitly wants that.
- Counts only PRs whose head is in this same repository and whose head ref
  starts with the prefix. The repository comparison ignores case, as GitHub
  owner and repository names do. Fork PRs, and PRs from deleted forks
  (``head.repo: null``), never count: these workflows only push same-repo
  branches.
- Fails closed: a missing or failing ``gh``, non-JSON or non-list page,
  malformed entry (including a ``head.repo`` without a string ``full_name``,
  or a non-integer or boolean ``number``), or more than ``MAX_PAGES`` pages
  exits 1 without a verdict.

Callers need ``GH_TOKEN`` with ``pull-requests: read`` (wired separately from
this helper).

Output: ``pending=true|false`` and ``pending_prs=<numbers>`` on stdout and, when
set, appended to ``$GITHUB_OUTPUT``. Exit 0 whenever a verdict was reached.
Only PR numbers are printed, never titles, bodies or branch names.
"""

import argparse
import json
import os
import subprocess
import sys

PER_PAGE = 100
MAX_PAGES = 50


class GuardError(Exception):
    """The pending state could not be established; callers must fail closed."""


def _gh_page(repo, base, page):
    query = "state=open" + (f"&base={base}" if base else "")
    path = f"repos/{repo}/pulls?{query}&per_page={PER_PAGE}&page={page}"
    try:
        r = subprocess.run(
            ["gh", "api", path], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise GuardError(f"gh could not be started on page {page}") from exc
    if r.returncode != 0:
        raise GuardError(f"gh api failed on page {page} (exit {r.returncode})")
    return r.stdout


def pending_prs(repo, prefix, base=None, fetch=_gh_page):
    """Return sorted numbers of same-repo open PRs whose head ref has prefix."""
    if not prefix:
        raise GuardError("empty branch prefix")
    found = []
    for page in range(1, MAX_PAGES + 1):
        raw = fetch(repo, base, page)
        try:
            items = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise GuardError(f"page {page} is not JSON") from exc
        if not isinstance(items, list):
            raise GuardError(f"page {page} is not a list")
        for pr in items:
            if not isinstance(pr, dict) or not isinstance(pr.get("head"), dict):
                raise GuardError(f"malformed PR entry on page {page}")
            head = pr["head"]
            head_repo = head.get("repo")
            if head_repo is None:
                continue  # deleted fork: cannot be one of our branches
            if not isinstance(head_repo, dict):
                raise GuardError(f"malformed head.repo on page {page}")
            full_name = head_repo.get("full_name")
            ref = head.get("ref")
            number = pr.get("number")
            if (
                not isinstance(full_name, str)
                or not isinstance(ref, str)
                or isinstance(number, bool)
                or not isinstance(number, int)
            ):
                raise GuardError(f"malformed PR entry on page {page}")
            if full_name.lower() == repo.lower() and ref.startswith(prefix):
                found.append(number)
        if len(items) < PER_PAGE:
            return sorted(found)
    raise GuardError(f"more than {MAX_PAGES} pages of open PRs")


def main(argv=None, fetch=_gh_page):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--base", default=None)
    args = ap.parse_args(argv)
    try:
        prs = pending_prs(args.repo, args.prefix, args.base, fetch=fetch)
    except GuardError as exc:
        print(f"::error::pending-PR guard failed closed: {exc}", file=sys.stderr)
        return 1
    lines = [
        f"pending={'true' if prs else 'false'}",
        "pending_prs=" + " ".join(str(n) for n in prs),
    ]
    print("\n".join(lines))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
