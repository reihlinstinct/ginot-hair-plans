#!/usr/bin/env python3
"""Guarded auto-merge for automated data PRs (issue #1037).

Scans open same-repo PRs from the four automated data producers
(permit-feed/, weekly-refresh/, mirror-ingest/, publications/ branch
prefixes) and merges without squashing at most ``--max-merges`` of them - only when
every gate passes:

1. Provenance: same-repo head with a producer branch prefix, authored by
   the repo owner (the automation account), not a draft, no
   ``no-automerge`` label.
2. Data-only paths: every changed file is ``data/*.json`` that already
   exists on the base branch, or one of the exact generated-site paths the
   producers stage. No deletions, renames, new data files, code, workflows
   or hand-written docs.
3. JSON sanity: every changed JSON parses on both sides, keeps its
   top-level type, keeps the exact dict key set, and stays within
   [0.5x, 3x] of the base list length.
4. Secrets/PII scan: every added diff line is free of token patterns,
   private-key headers, password assignments, email addresses,
   checksum-valid Israeli ID numbers and Israeli phone numbers.
5. Green CI at the exact head sha (all check runs completed
   success/neutral/skipped), PR mergeable, no CHANGES_REQUESTED review at
   the head.
6. Non-squash merge via the API bound to the validated head sha - a moved head
   makes GitHub reject the call.

Fail-closed: any API error, unexpected shape or failed check skips the PR
for the normal manual review path. Nothing is force-pushed or closed.

Audit comment posts from the script; the merge itself is a gated
workflow step in data-automerge.yml (allowlisted in
tests/test_no_review_bypass.py) so no ci script can merge on its own.

Usage: data_pr_automerge.py --repo OWNER/NAME [--max-merges N] [--dry-run]
Env: GH_TOKEN with contents+pull-requests write (the refresh PAT).
Writes merge_pr/merge_sha/merge_title to $GITHUB_OUTPUT for the merge
step when the first eligible PR is found. Exit 0 with a per-PR report;
exit 1 only on internal/API failure.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ginot import i18n

GH_TIMEOUT_SECONDS = 60
MAX_PAGES = 10
MERGE_CONCLUSIONS = {"success", "neutral", "skipped"}
PRODUCER_PREFIXES = (
    "permit-feed/",
    "weekly-refresh/",
    "mirror-ingest/",
    "publications/",
    "mavat-check/",
)
OPT_OUT_LABEL = "no-automerge"

_LOCALE_PAGES = tuple(
    f"docs/{lang}/{page}"
    for lang in i18n.lang_codes()
    if lang != i18n.default_lang()
    for page in ("index.html", "permits.html", "permits-default.html")
)
ALLOWED_DOCS_EXACT = frozenset(
    {
        "docs/index.json",
        "docs/index.html",
        "docs/data.json",
        "docs/permit-ids.json",
        "docs/permit-points.json",
        "docs/permits.html",
        "docs/permits-default.html",
        "docs/publications_active.json",
        # #121 versioned API outputs, staged by permit-feed publication
        # commits (#1065); same generated-data class as the pages above.
        "docs/api/v1/plans.json",
        "docs/api/v1/permits.json",
        "docs/api/v1/changes.json",
        "docs/api/v1/meta.json",
    }
    | set(_LOCALE_PAGES)
)
BADGE_RE = re.compile(r"docs/badge/parcel-[A-Za-z0-9._-]+\.json\Z")
DATA_JSON_RE = re.compile(r"data/[A-Za-z0-9._-]+\.json\Z")

SECRET_RES = tuple(
    re.compile(pattern, flags)
    for pattern, flags in (
        (r"ghp_[A-Za-z0-9]{20,}", 0),
        (r"github_pat_[A-Za-z0-9_]{20,}", 0),
        (r"gh[ousr]_[A-Za-z0-9]{20,}", 0),
        (r"sk-[A-Za-z0-9]{20,}", 0),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", 0),
        (r"[\"']?password[\"']?\s*[:=]", re.IGNORECASE),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", 0),
        (r"\b0\d{1,2}-?\d{7}\b", 0),
    )
)
IL_ID_RE = re.compile(r"\b\d{9}\b")
LIST_SHRINK_FLOOR = 0.5
LIST_GROWTH_CEILING = 3.0


def gh_api(path: str, method: str = "GET", payload: dict | None = None) -> object:
    """One gh api call, fail-closed: errors raise RuntimeError."""
    command = ["gh", "api", "--method", method, path]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {result.stderr.strip()[:200]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"gh api {path} returned non-JSON") from error


def file_text_at_ref(repo: str, filename: str, ref: str) -> str:
    """Decoded file text at a ref.

    The contents API omits `content` for files over 1MB (e.g.
    data/permit_mirror.json); fall back to the git blob API, which serves
    the same bytes for blobs up to 100MB. Fail closed when neither path
    yields text.
    """
    import base64

    root = f"repos/{repo}/contents/{urllib.parse.quote(filename)}"
    payload = gh_api(f"{root}?ref={urllib.parse.quote(ref)}")
    content = payload.get("content") if isinstance(payload, dict) else None
    if content:
        return base64.b64decode(content).decode("utf-8")
    sha = payload.get("sha") if isinstance(payload, dict) else None
    if not sha:
        raise RuntimeError(f"no content or blob sha for {filename}@{ref}")
    blob = gh_api(f"repos/{repo}/git/blobs/{sha}")
    blob_content = blob.get("content") if isinstance(blob, dict) else None
    if not blob_content:
        raise RuntimeError(f"empty blob for {filename}@{ref}")
    return base64.b64decode(blob_content).decode("utf-8")


def gh_api_paginated(path: str) -> list:
    """Paginate a list endpoint, fail-closed on shape errors or overflow."""
    separator = "&" if "?" in path else "?"
    items: list = []
    for page in range(1, MAX_PAGES + 1):
        chunk = gh_api(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(chunk, list):
            raise TypeError(f"gh api {path} page {page} was not a list")
        items.extend(chunk)
        if len(chunk) < 100:
            return items
    raise RuntimeError(f"gh api {path} exceeded {MAX_PAGES} pages")


def path_allowed(filename: str, status: str, base_files: set[str]) -> str | None:
    """None when the path is inside the data-only allowlist, else a reason."""
    if status != "modified" and not (status == "added" and BADGE_RE.match(filename)):
        return f"status {status!r} is not allowed for {filename}"
    if filename in ALLOWED_DOCS_EXACT:
        return None
    if BADGE_RE.match(filename):
        return None
    if DATA_JSON_RE.match(filename):
        if filename in base_files:
            return None
        return f"new data file {filename} is not allowed"
    return f"path {filename} is outside the data-only allowlist"


def json_sane(path: str, base_text: str, head_text: str) -> str | None:
    """None when the JSON change is structurally sane, else a reason."""
    try:
        base = json.loads(base_text)
        head = json.loads(head_text)
    except json.JSONDecodeError as error:
        return f"{path} no longer parses as JSON: {error}"
    if type(base) is not type(head):
        return f"{path} changed top-level type"
    if isinstance(base, dict):
        if set(base) != set(head):
            return f"{path} changed top-level keys"
    elif isinstance(base, list):
        if (
            base
            and not LIST_SHRINK_FLOOR <= len(head) / len(base) <= LIST_GROWTH_CEILING
        ):
            return f"{path} list length {len(base)} -> {len(head)} out of bounds"
        if not base and head:
            return f"{path} list grew from empty"
    return None


def il_id_valid(digits: str) -> bool:
    """Israeli ID checksum: even positions doubled, digit-summed, mod 10."""
    total = 0
    for index, char in enumerate(digits):
        value = int(char) * (2 if index % 2 else 1)
        total += value // 10 + value % 10
    return total % 10 == 0


def added_lines(base_text: str, head_text: str) -> list[str]:
    """Lines added between two file versions: the secrets/PII scan input for
    oversized diff entries, whose patch GitHub omits."""
    return [
        line[1:]
        for line in difflib.unified_diff(
            base_text.splitlines(), head_text.splitlines(), lineterm="", n=0
        )
        if line.startswith("+") and not line.startswith("+++")
    ]


def added_line_clean(line: str) -> str | None:
    """None when an added diff line is free of secrets/PII, else a reason."""
    for pattern in SECRET_RES:
        if pattern.search(line):
            return f"secret/PII pattern {pattern.pattern!r}"
    for match in IL_ID_RE.finditer(line):
        if il_id_valid(match.group()):
            return "checksum-valid Israeli ID number"
    return None


def check_pr(repo: str, pr: dict, base_files: set[str]) -> list[str]:
    """Return the list of gate failures for one candidate PR (empty = ok)."""
    reasons: list[str] = []
    head = pr.get("head") or {}
    head_repo = head.get("repo") or {}
    if head_repo.get("full_name", "").lower() != repo.lower():
        return ["fork or cross-repo head"]
    if not str(head.get("ref", "")).startswith(PRODUCER_PREFIXES):
        return ["branch prefix is not a data producer"]
    if (pr.get("user") or {}).get("login", "").lower() != repo.split("/")[0].lower():
        return ["author is not the automation account"]
    if pr.get("draft"):
        return ["draft PR"]
    labels = {label.get("name") for label in pr.get("labels") or []}
    if OPT_OUT_LABEL in labels:
        return [f"{OPT_OUT_LABEL} label set"]
    number = pr["number"]
    head_sha = head.get("sha", "")

    detail = gh_api(f"repos/{repo}/pulls/{number}")
    if detail.get("mergeable") is not True:
        reasons.append(f"mergeable={detail.get('mergeable')}")
    reviews = gh_api_paginated(f"repos/{repo}/pulls/{number}/reviews")
    if any(
        review.get("state") == "CHANGES_REQUESTED"
        and review.get("commit_id") == head_sha
        for review in reviews
    ):
        reasons.append("CHANGES_REQUESTED review at head")

    files = gh_api_paginated(f"repos/{repo}/pulls/{number}/files")
    if not files:
        reasons.append("empty diff")
    for entry in files:
        filename = entry.get("filename", "")
        reason = path_allowed(filename, entry.get("status", ""), base_files)
        if reason:
            reasons.append(reason)
            continue
        # Oversized diff entries carry no patch: fetch both blobs once and
        # compute the added lines locally, so the secrets/PII scan still
        # runs (skipping the scan for big data files would silence it
        # exactly where it matters). Fetch/decode failures raise and the
        # per-PR catch skips this PR (fail closed).
        base_text = head_text = None
        patch = entry.get("patch")
        if patch is None or filename.endswith(".json"):
            base_text = file_text_at_ref(repo, filename, pr["base"]["ref"])
            head_text = file_text_at_ref(repo, filename, head_sha)
        added = (
            added_lines(base_text, head_text)
            if patch is None
            else [
                line[1:]
                for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
        )
        for line in added:
            hit = added_line_clean(line)
            if hit:
                reasons.append(f"{filename}: {hit}")
        if filename.endswith(".json"):
            sane = json_sane(filename, base_text, head_text)
            if sane:
                reasons.append(sane)

    runs = gh_api(f"repos/{repo}/commits/{head_sha}/check-runs?per_page=100")
    check_runs = runs.get("check_runs", []) if isinstance(runs, dict) else []
    if not check_runs:
        reasons.append("no check runs at head")
    elif len(check_runs) >= 100:
        reasons.append("check-run page overflow")
    else:
        for run in check_runs:
            if run.get("status") != "completed":
                reasons.append(f"check {run.get('name')} still {run.get('status')}")
            elif run.get("conclusion") not in MERGE_CONCLUSIONS:
                reasons.append(f"check {run.get('name')} = {run.get('conclusion')}")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--max-merges", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("GH_TOKEN"):
        print("FAIL: GH_TOKEN is required")
        return 1

    owner = args.repo.split("/")[0]
    base_ref = "main"
    try:
        pulls = [
            pr
            for pr in gh_api_paginated(f"repos/{args.repo}/pulls?state=open")
            if (pr.get("head") or {}).get("repo")
            and (pr["head"]["repo"].get("full_name", "").lower() == args.repo.lower())
            and str(pr["head"].get("ref", "")).startswith(PRODUCER_PREFIXES)
            and (pr.get("user") or {}).get("login", "").lower() == owner.lower()
        ]
        base_tree = gh_api(f"repos/{args.repo}/git/trees/{base_ref}?recursive=1")
        base_files = {
            entry["path"] for entry in base_tree.get("tree", []) if "path" in entry
        }
        if base_tree.get("truncated"):
            raise RuntimeError("base tree listing truncated")
    except (RuntimeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1

    merged = 0
    for pr in sorted(pulls, key=lambda item: item["number"]):
        number, head_sha = pr["number"], pr["head"]["sha"]
        try:
            reasons = check_pr(args.repo, pr, base_files)
        # ValueError covers base64/UTF-8 decode failures from the blob
        # fallback: one malformed file must skip its PR, never abort the
        # whole sweep (review follow-up, #1061).
        except (RuntimeError, KeyError, ValueError) as error:
            reasons = [f"guard error: {error}"]
        if reasons:
            print(f"PR #{number}: SKIP - " + "; ".join(reasons))
            continue
        if merged >= args.max_merges:
            print(f"PR #{number}: eligible, held by --max-merges={args.max_merges}")
            continue
        if args.dry_run:
            print(f"PR #{number}: eligible (dry run, not merged)")
            merged += 1
            continue
        summary = (
            "Auto-merge guard passed (refs #1037): data-only paths, JSON "
            "sanity, secrets/PII scan clean, CI green at "
            f"{head_sha}. The gated merge step in data-automerge.yml "
            "preserves the source commits with a non-squash merge bound to this sha."
        )
        try:
            gh_api(
                f"repos/{args.repo}/issues/{number}/comments",
                method="POST",
                payload={"body": summary},
            )
        except RuntimeError as error:
            print(f"PR #{number}: audit comment failed: {error}")
            continue
        output_path = os.environ.get("GITHUB_OUTPUT")
        if output_path:
            with open(output_path, "a", encoding="utf-8") as output:
                output.write(f"merge_pr={number}\n")
                output.write(f"merge_sha={head_sha}\n")
                output.write(f"merge_title={pr['title']} (#{number})\n")
        print(
            f"PR #{number}: eligible at {head_sha} (merge step gated on the kill switch)"
        )
        merged += 1
        if merged >= args.max_merges:
            break
    print(f"done: {merged} eligible, {len(pulls)} candidate(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
