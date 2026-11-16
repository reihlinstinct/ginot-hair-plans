#!/usr/bin/env python3
"""Fail early when a publication commit leaves docs/ changes behind (#874).

permit-feed.yml regenerates the site and stages an explicit, narrow list of
generated permit paths before committing the publication bundle. A covered
docs-fresh output (or an orphan deletion, or a brand-new rendered file) that
changes outside that list would stay unstaged and the bundle would only fail
docs-fresh later, in PR CI. This check runs right after the publication
commit and fails the run while the evidence is still in the runner.

Contract: after the publication commit, docs/ must be completely clean -
no modified or deleted tracked files and no untracked files. The fix for a
failure is never to widen this check; either teach the renderer or stage the
specific path explicitly in the workflow.

Standard library only; no network. Usage:
    python scripts/ci/check_publication_clean.py [--root DIR]
Exit 0 when docs/ is clean, 1 with one line per leftover path otherwise.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

GIT_LOCATION_VARIABLES = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_IMPLICIT_WORK_TREE",
    }
)


def git_environment() -> dict[str, str]:
    """Isolate repository location while preserving Git configuration."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in GIT_LOCATION_VARIABLES
    }


def git(root, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=git_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def leftovers(root) -> list[str]:
    """Paths under docs/ with uncommitted state; paths only, never content.

    --untracked-files=all sweeps newly rendered (untracked) files too,
    not only modified or deleted tracked ones.
    """
    out = []
    for line in git(
        root, "status", "--porcelain", "--untracked-files=all", "--", "docs/"
    ).splitlines():
        if line:
            out.append(line[3:].strip())
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    out = leftovers(args.root)
    if not out:
        print("publication clean: no leftover docs/ changes")
        return 0
    print("publication commit left docs/ changes unstaged (issue #874):")
    for path in sorted(set(out)):
        print(f"  {path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
