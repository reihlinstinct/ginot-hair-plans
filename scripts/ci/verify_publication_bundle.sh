#!/usr/bin/env bash
# Issue #567: fail-closed check of the permit-feed publication bundle before
# any publication token is in the environment.
#
# The renderer job runs third-party Python (wheels and their .pth startup
# code) and so is treated as untrusted. It hands over exactly one commit as a
# git bundle. This script, run from trusted main in a fresh job with no Python
# step, accepts the bundle only if:
#   - it verifies against the local history (its prerequisite is present),
#   - it carries one head whose commit has exactly one parent,
#   - that parent is an ancestor of (or equal to) BASE,
#   - every changed path is a regular file in the generated-data allowlist
#     (no symlinks, no submodules, no code or workflow paths).
# On success it prints the accepted commit SHA; on any failure it exits
# non-zero and prints the reason to stderr.
#
# usage: verify_publication_bundle.sh BUNDLE [BASE]   (BASE default origin/main)
set -euo pipefail

fail() { echo "publication bundle rejected: $*" >&2; exit 1; }

bundle=${1:?usage: verify_publication_bundle.sh BUNDLE [BASE]}
base=${2:-origin/main}

[ -f "$bundle" ] || fail "missing bundle file"
git rev-parse --verify -q "$base^{commit}" >/dev/null || fail "base $base not found"
git bundle verify -q "$bundle" >/dev/null 2>&1 || fail "bundle does not verify against local history"

heads=$(git bundle list-heads "$bundle")
[ "$(printf '%s\n' "$heads" | grep -c .)" = 1 ] || fail "expected exactly one head"
tip=${heads%% *}
[[ $tip =~ ^[0-9a-f]{40}$ ]] || fail "malformed head"

git fetch -q --no-tags "$bundle" "${heads#* }" || fail "cannot fetch bundle head"
[ "$(git rev-parse FETCH_HEAD)" = "$tip" ] || fail "fetched head does not match bundle head"

read -r -a parents <<<"$(git rev-list --parents -n 1 "$tip")"
[ "${#parents[@]}" = 2 ] || fail "commit must have exactly one parent"
parent=${parents[1]}
git merge-base --is-ancestor "$parent" "$base" || fail "parent is not on $base"

allowed='^(data/.+|docs/index\.json|docs/badge/parcel-[^/]+\.json|docs/permits\.html|docs/permits-default\.html|docs/permit-ids\.json|docs/permit-points\.json)$'
count=0
while IFS= read -r -d '' meta && IFS= read -r -d '' path; do
  count=$((count + 1))
  newmode=${meta#:}
  newmode=${newmode#* }
  newmode=${newmode%% *}
  case "$newmode" in
    100644|000000) ;;  # regular file, or deletion
    *) fail "disallowed file mode $newmode for $path" ;;
  esac
  [[ $path =~ $allowed ]] || fail "path outside the publication allowlist: $path"
  case "/$path/" in */../*|*/./*) fail "non-canonical path: $path" ;; esac
done < <(git diff-tree -r -z --raw --no-commit-id "$parent" "$tip")
[ "$count" -gt 0 ] || fail "commit changes nothing"

echo "$tip"
