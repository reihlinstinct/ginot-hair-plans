#!/usr/bin/env bash
# Isolated JSON-only branch; never changes main or dispatches scan workflows.
set -euo pipefail
cp "$1"/tests.json /tmp/tests-badge.json
cp "$1"/coverage.json /tmp/coverage-badge.json
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

publish() {
  cp /tmp/tests-badge.json "$WORK/tests.json"
  cp /tmp/coverage-badge.json "$WORK/coverage.json"
  git -C "$WORK" add tests.json coverage.json
  if git -C "$WORK" diff --cached --quiet; then
    return 1 # nothing new to publish
  fi
  git -C "$WORK" commit -m 'data: measured successful main CI badges' >/dev/null
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
