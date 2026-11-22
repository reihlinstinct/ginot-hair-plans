#!/usr/bin/env python3
"""Informational report: review threads on a PR and their disposition (#454).

The written rule (design/ai-review-findings.md) says every review finding is
fixed (commit named in the thread) or rejected (one-line reason) before merge.
This script makes the state visible in the run summary: per thread, who
started it, whether it is resolved, and whether anyone answered it. It is
read-only (GraphQL query with the workflow's GITHUB_TOKEN, contents and
pull-requests read), writes only the step summary, never posts, resolves or
commits anything, and exits 0 unless --strict is given. Review text is
external content: it is shown as a single truncated plain line and never
interpreted.

Usage: review_threads.py --repo OWNER/NAME --pr N [--strict]
Environment: GITHUB_TOKEN, optional GITHUB_STEP_SUMMARY."""

import argparse
import json
import os
import re
import urllib.request

QUERY = """
query($owner:String!,$name:String!,$pr:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      reviewThreads(first:100){
        nodes{
          isResolved isOutdated path
          comments(first:20){nodes{author{login __typename} body}}
        }
      }
    }
  }
}"""

SNIPPET_CHARS = 90


def fetch(repo, pr, token):
    """Return the raw reviewThreads nodes for a PR (one GraphQL call)."""
    owner, name = repo.split("/", 1)
    payload = json.dumps(
        {"query": QUERY, "variables": {"owner": owner, "name": name, "pr": pr}}
    ).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    # Fixed https GitHub API URL, never user-controlled.
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(
            "GraphQL error: " + str(data["errors"][0].get("message", ""))[:120]
        )
    return data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]


def _snippet(body):
    """One plain, truncated line; markup and HTML comments are dropped."""
    text = re.sub(r"<!--.*?-->", " ", body or "", flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[|`\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:SNIPPET_CHARS]


def classify(thread):
    """Return (state, starter, is_bot). State is one of:
    resolved, answered (reply by someone other than the starter), unanswered."""
    comments = (thread.get("comments") or {}).get("nodes") or []
    first = comments[0] if comments else {}
    author = first.get("author") or {}
    starter = author.get("login") or "unknown"
    is_bot = author.get("__typename") == "Bot"
    if thread.get("isResolved"):
        return "resolved", starter, is_bot
    replied = any(
        (c.get("author") or {}).get("login") not in (None, starter)
        for c in comments[1:]
    )
    return ("answered" if replied else "unanswered"), starter, is_bot


def summarize(threads, pr):
    """Return (markdown, counts) for the given thread nodes."""
    counts = {"resolved": 0, "answered": 0, "unanswered": 0, "bot_unanswered": 0}
    rows = []
    for t in threads:
        state, starter, is_bot = classify(t)
        counts[state] += 1
        if state == "unanswered" and is_bot:
            counts["bot_unanswered"] += 1
        comments = (t.get("comments") or {}).get("nodes") or []
        first_body = comments[0].get("body") if comments else ""
        rows.append(
            f"| {state} | {starter}{' (bot)' if is_bot else ''} "
            f"| {'outdated' if t.get('isOutdated') else 'current'} "
            f"| {_snippet(t.get('path'))} | {_snippet(first_body)} |"
        )
    lines = [f"### Review threads on #{pr} (informational)", ""]
    if not threads:
        lines.append("No review threads.")
    else:
        head = (
            f"{len(threads)} thread(s): {counts['resolved']} resolved, "
            f"{counts['answered']} answered, {counts['unanswered']} unanswered "
            f"({counts['bot_unanswered']} from a bot)."
        )
        rule = (
            "Rule (design/ai-review-findings.md): each finding is fixed "
            "(commit named in the thread) or rejected (one-line reason) "
            "before merge. This report only shows the state; it changes "
            "nothing."
        )
        lines += [
            head,
            "",
            rule,
            "",
            "| State | Started by | Anchor | File | First comment |",
            "|---|---|---|---|---|",
        ] + rows
        if len(threads) >= 100:
            lines += ["", "Only the first 100 threads were read."]
    return "\n".join(lines) + "\n", counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    text, counts = summarize(
        fetch(args.repo, args.pr, os.environ["GITHUB_TOKEN"]), args.pr
    )
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    if args.strict and counts["unanswered"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
