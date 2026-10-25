#!/usr/bin/env python3
"""CI guard: noreply-pattern commit identities must not resolve to non-owned
GitHub accounts (issue #473).

GitHub resolves <username>@users.noreply.github.com (and the ID+ form) to the
account holding that username. A typo'd or misconfigured git identity silently
attributes our commits to a stranger (incident 2026-10-25: commit 1bfaed94 in
PR #432 linked to the unrelated @instinct account).

Rule for every commit in --base..--head, applied to BOTH author and committer:
- noreply-pattern email: the captured username must be in OWNED, or - for a
  fork PR only - equal the PR author's own login (--fork-author).
- any other email: not resolvable offline; passes by design (linking requires
  the address owner to verify it on their own account).

Usage: check_commit_identities.py --base REF [--head REF] [--fork-author LOGIN]

History completeness is fail-closed: if the base..head walk hits a shallow
boundary (truncated clone/fetch), the guard reports a problem instead of
passing on a partial commit set."""

import argparse
import pathlib
import re
import subprocess
import sys

NOREPLY = re.compile(r"^(?:\d+\+)?([^@+]+)@users\.noreply\.github\.com$", re.IGNORECASE)

# Accounts whose noreply identities are expected on this repo's commits.
# Bot noreply forms carry the [bot] suffix as the captured username.
OWNED = frozenset(
    {
        "reihlinstinct",
        "reihl",
        "reihl-tab",
        "github-actions[bot]",
        "dependabot[bot]",
    }
)


def violations(records, owned=OWNED, fork_author=None):
    """records: iterable of (sha, author_email, committer_email).
    Returns a list of human-readable problem strings."""
    problems = []
    allowed = {o.lower() for o in owned}
    fork_login = fork_author.lower() if fork_author else None
    for sha, author_email, committer_email in records:
        for role, email in (("author", author_email), ("committer", committer_email)):
            m = NOREPLY.match(email or "")
            if not m:
                continue  # non-noreply: cannot resolve offline, out of scope
            username = m.group(1).lower()
            if username in allowed:
                continue
            if fork_login and username == fork_login:
                continue  # a fork author's own self-noreply is legitimate
            problems.append(
                f"{sha[:8]} {role} email {email!r} resolves to GitHub account "
                f"{m.group(1)!r}, which is not an owned identity of this repo"
            )
    return problems


def commit_records(base, head):
    fmt = "%H%x00%ae%x00%ce"
    r = subprocess.run(
        ["git", "log", f"--format={fmt}", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        sha, ae, ce = line.split("\x00")
        out.append((sha, ae, ce))
    return out


def _is_ancestor(anc, desc):
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", anc, desc],
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


def boundary_commits(base, head):
    """Grafted (shallow-cut) commits inside the base..head range. A grafted
    commit's parents are missing, so the walk silently stops there; a
    non-empty result means commit_records saw only part of the range.
    (rev-list --boundary does not flag graft cuts, so detect them directly:
    an entry in .git/shallow that is an ancestor of head but not of base.)"""
    path = subprocess.run(
        ["git", "rev-parse", "--git-path", "shallow"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    try:
        cuts = [l.strip() for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    except FileNotFoundError:
        return []  # no shallow file: history is complete
    return [c for c in cuts if _is_ancestor(c, head) and not _is_ancestor(c, base)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--fork-author", default="")
    args = ap.parse_args(argv)
    problems = []
    truncated = boundary_commits(args.base, args.head)
    if truncated:
        problems.append(
            f"history truncated at shallow boundary ({len(truncated)} boundary "
            f"commit(s), first {truncated[0][:8]}): refusing to pass on a "
            "partial commit set - fetch full history"
        )
    records = commit_records(args.base, args.head)
    problems += violations(records, fork_author=args.fork_author or None)
    for p in problems:
        print("FAIL:", p)
    print(f"checked {len(records)} commits, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
