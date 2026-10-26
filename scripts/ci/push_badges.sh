#!/usr/bin/env bash
# Isolated JSON-only branch; never changes main or dispatches scan workflows.
set -euo pipefail
STAGE=$(mktemp -d) # private staging: no predictable shared /tmp paths
trap 'rm -rf "$STAGE"' EXIT
cp "$1"/tests.json "$STAGE/tests.json"
cp "$1"/coverage.json "$STAGE/coverage.json"
WORK=$(mktemp -d)
git fetch origin badge-data || true
if git show-ref --verify --quiet refs/remotes/origin/badge-data; then
  git worktree add "$WORK" origin/badge-data
else
  git worktree add --detach "$WORK" HEAD
  git -C "$WORK" switch --orphan badge-data
  git -C "$WORK" rm -rf --ignore-unmatch .
fi
git -C "$WORK" config user.name 'github-actions[bot]'
git -C "$WORK" config user.email '41898282+github-actions[bot]@users.noreply.github.com'

# Returns 1 only for a clean index (nothing new to publish); every real
# failure is an explicit fatal exit - publish runs in condition context,
# where set -e would otherwise mask a failed cp/add/commit as "no changes".
publish() {
  cp "$STAGE/tests.json" "$WORK/tests.json" || {
    echo "badge staging copy failed" >&2
    exit 1
  }
  cp "$STAGE/coverage.json" "$WORK/coverage.json" || {
    echo "badge staging copy failed" >&2
    exit 1
  }
  git -C "$WORK" add tests.json coverage.json || {
    echo "badge git add failed" >&2
    exit 1
  }
  if git -C "$WORK" diff --cached --quiet; then
    return 1 # nothing new to publish
  fi
  git -C "$WORK" commit -m 'data: measured successful main CI badges' >/dev/null || {
    echo "badge commit failed" >&2
    exit 1
  }
  return 0
}

if publish; then
  # Two overlapping main runs race on this push (issue #497): re-fetch,
  # reset onto the winner's commit, re-apply our measured files, retry.
  for attempt in 1 2 3; do
    if git -C "$WORK" push origin HEAD:badge-data; then
      exit 0
    fi
    echo "badge-data push raced (attempt $attempt) - re-fetching and re-applying" >&2
    git -C "$WORK" fetch origin badge-data
    git -C "$WORK" reset --hard origin/badge-data
    publish || exit 0 # the racing push already carried identical data
  done
  echo "badge-data push raced 3 times - failing" >&2
  exit 1
fi
