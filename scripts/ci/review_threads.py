#!/usr/bin/env python3
"""Informational report: review threads on a PR and their disposition (#454).

The written rule (design/ai-review-findings.md) says every review finding is
fixed (commit named in the thread) or rejected (one-line reason) before merge.
This script makes the state visible in the run summary: per thread, who
started it, whether it is resolved, and whether anyone answered it. It is
read-only (GraphQL query with the workflow's GITHUB_TOKEN, contents and
pull-requests read), writes only the step summary, never posts, resolves or
commits anything, and exits 0 unless --strict is given. A failed fetch (network,
HTTP, GraphQL or response shape) is reported as unavailable and also exits 0,
so the advisory report does not hold a PR or the guarded data automerge.
A reply by a bot alone is shown as such, and a commit-like id or a rejection
note in a reply is shown as an observed marker, not as verification. Review text is
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
        pageInfo{hasNextPage}
        nodes{
          isResolved isOutdated path
          comments(first:20){pageInfo{hasNextPage} nodes{author{login __typename} body}}
        }
      }
    }
  }
}"""

REVIEWS_QUERY = """
query($owner:String!,$name:String!,$pr:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      headRefOid
      reviews(last:50){
        pageInfo{hasPreviousPage}
        nodes{author{login} state commit{oid} body}
      }
    }
  }
}"""

SNIPPET_CHARS = 90


def fetch(repo, pr, token):
    """Return (thread nodes, more_threads_exist) for a PR (one GraphQL call)."""
    owner, name = repo.split("/", 1)
    data = _graphql(QUERY, {"owner": owner, "name": name, "pr": pr}, token)
    block = data["repository"]["pullRequest"]["reviewThreads"]
    return block["nodes"], bool((block.get("pageInfo") or {}).get("hasNextPage"))


def _graphql(query, variables, token):
    payload = json.dumps({"query": query, "variables": variables}).encode()
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
    return data["data"]


def fetch_reviews(repo, pr, token):
    """Return (head sha, review nodes, more_reviews_exist) for a PR."""
    owner, name = repo.split("/", 1)
    data = _graphql(REVIEWS_QUERY, {"owner": owner, "name": name, "pr": pr}, token)[
        "repository"
    ]["pullRequest"]
    block = data["reviews"]
    more = bool((block.get("pageInfo") or {}).get("hasPreviousPage"))
    return data["headRefOid"], block["nodes"], more


# The verdict is read from a line that starts with the word, never from prose
# that merely mentions it, and the last such line wins (the formal verdict
# closes a review). Decoration such as bullets, bold, dashes is skipped.
_VERDICT = re.compile(
    r"^[\s>*_-]*verdict\b([^\n]{0,120})", re.IGNORECASE | re.MULTILINE
)
_VERDICT_WORDS = (
    "PASSED",
    "PASS",
    "FINDINGS",
    "CHANGES REQUESTED",
    "BLOCKED",
    "FAIL",
    "APPROVED",
    "APPROVE",
)
_WITH_FOLLOWUPS = re.compile(r"\bwith\s+follow-?\s?ups?\b", re.IGNORECASE)
_FINDING = re.compile(
    r"^\s*[-*]?\s*\**(P[0-3]|Minor)\b([^:\n]{0,60}):\**\s*(\S.*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Outcome words ("fixed", "resolved") are never read as resolution: the
# script cannot tell "fixed" from "not fixed", so every finding line counts.


def _verdict_word(body):
    """Return the closing verdict as a short phrase: PASS, FINDINGS, CHANGES
    REQUESTED, etc., plus 'with follow-ups' when the line says so; '-' if
    no verdict line exists."""
    # The newest verdict line that yields a known word wins, so a later prose
    # line that merely starts with "Verdict" cannot hide the formal one.
    for rest in reversed(_VERDICT.findall(body or "")):
        # A parenthetical qualifier may contain a colon: drop it first.
        rest = re.sub(r"^\s*\([^)]*\)", "", rest)
        # A plain qualifier before the colon ("Verdict on the delta: PASS").
        if ":" in rest:
            rest = rest.split(":", 1)[1]
        text = re.sub(r"^[^A-Za-z]+", "", rest)
        upper = re.sub(r"[^A-Z ]", " ", text.upper()).strip()
        word = next((w for w in _VERDICT_WORDS if re.match(w + r"\b", upper)), None)
        if word is None:
            continue
        if word in ("PASSED",):
            word = "PASS"
        if _WITH_FOLLOWUPS.search(text):
            word += " with follow-ups"
        return word
    return "-"


def review_facts(review, head):
    """Observed facts from one review body: (reviewer, state, on_current_head,
    verdict word, finding lines that are not 'none'). All of it is text the
    reviewer wrote; none of it is verified here."""
    author = review.get("author") or {}
    body = review.get("body") or ""
    verdict = _verdict_word(body)
    claimed = {}
    for tag, _mid, text in _FINDING.findall(body):
        if re.match(r"\W*none\b", text, re.IGNORECASE):
            continue
        key = tag.upper() if tag.upper().startswith("P") else "Minor"
        claimed[key] = claimed.get(key, 0) + 1
    on_head = ((review.get("commit") or {}).get("oid") or "") == head
    return (
        author.get("login") or "unknown",
        review.get("state") or "-",
        on_head,
        verdict,
        claimed,
    )


def summarize_reviews(head, reviews, more=False):
    """Markdown section for review bodies, or '' when there are none."""
    rows = []
    for r in reviews:
        if not (r.get("body") or "").strip():
            continue
        who, state, on_head, verdict, claimed = review_facts(r, head)
        found = ", ".join(f"{k} x{v}" for k, v in sorted(claimed.items())) or "-"
        rows.append(
            f"| {_cell(who)} | {_cell(state)} | "
            f"{'current head' if on_head else 'older head'} | "
            f"{_cell(verdict)} | {found} |"
        )
    if not rows:
        return ""
    note = (
        "Verdict word and finding lines are read from what the reviewer wrote. "
        "Only lines that start with P0-P3 or Minor and a colon are parsed, and "
        "lines that say none are skipped, so findings written as prose are not "
        "counted. Nothing here checks that a finding was fixed or rejected, and "
        "a review on an older head may not cover the current one."
    )
    lines = [
        "",
        "#### Review bodies (observed text, not verified)",
        "",
        note,
        "",
        "| Reviewer | State | Reviewed | Verdict word | Finding lines parsed |",
        "|---|---|---|---|---|",
    ] + rows
    if more:
        lines += ["", "Only the newest 50 reviews were read."]
    return "\n".join(lines) + "\n"


def _snippet(body):
    """One plain, truncated line; markup and HTML comments are dropped."""
    text = re.sub(r"<!--.*?-->", " ", body or "", flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", "(link)", text)
    text = re.sub(r"[|`\[\]*_~#>\\!]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:SNIPPET_CHARS]


def _cell(text):
    """A table cell for a value that is data, not prose (a file path): only
    the pipe and line breaks are neutralised and the length is capped, so
    underscores and dots survive and the path stays accurate."""
    text = re.sub(r"[|\s]+", " ", text or "").strip()
    return text[:SNIPPET_CHARS]


_FIX_REF = re.compile(r"\b[0-9a-f]{7,40}\b")
_REJECT = re.compile(r"\b(rejected|won't fix|wontfix|not a bug)\b", re.IGNORECASE)


def marker(thread):
    """Observed marker in the replies, never a verification: 'commit ref'
    when a reply contains a hex id that looks like a commit, 'rejection
    note' when it says rejected / won't fix, else '-'. Whether the fix or the
    reason is real is not checked here."""
    comments = (thread.get("comments") or {}).get("nodes") or []
    text = " ".join((c.get("body") or "") for c in comments[1:])
    if _FIX_REF.search(text):
        return "commit ref"
    if _REJECT.search(text):
        return "rejection note"
    return "-"


def classify(thread):
    """Return (state, starter, is_bot). State is one of:
    resolved, answered (reply by a human other than the starter),
    bot-reply-only (replies exist but all are from bots, so no human
    disposition is shown), unanswered,
    incomplete (more comments exist than were read, so it is not judged)."""
    comments = (thread.get("comments") or {}).get("nodes") or []
    first = comments[0] if comments else {}
    author = first.get("author") or {}
    starter = author.get("login") or "unknown"
    is_bot = author.get("__typename") == "Bot"
    if thread.get("isResolved"):
        return "resolved", starter, is_bot
    if ((thread.get("comments") or {}).get("pageInfo") or {}).get("hasNextPage"):
        # Only the first 20 comments were read: a later reply may exist.
        return "incomplete", starter, is_bot
    others = [
        c.get("author") or {}
        for c in comments[1:]
        if (c.get("author") or {}).get("login") not in (None, starter)
    ]
    if any(a.get("__typename") != "Bot" for a in others):
        return "answered", starter, is_bot
    return ("bot-reply-only" if others else "unanswered"), starter, is_bot


def summarize(threads, pr, more_threads=False):
    """Return (markdown, counts) for the given thread nodes."""
    counts = {
        "resolved": 0,
        "answered": 0,
        "unanswered": 0,
        "bot-reply-only": 0,
        "incomplete": 0,
        "bot_unanswered": 0,
    }
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
            f"| {_cell(t.get('path'))} | {marker(t)} | {_snippet(first_body)} |"
        )
    lines = [f"### Review threads on #{pr} (informational)", ""]
    if not threads:
        lines.append("No review threads.")
    else:
        head = (
            f"{len(threads)} thread(s): {counts['resolved']} resolved, "
            f"{counts['answered']} answered by a human, "
            f"{counts['bot-reply-only']} with bot replies only, "
            f"{counts['unanswered']} unanswered "
            f"({counts['bot_unanswered']} from a bot), "
            f"{counts['incomplete']} not judged (more than 20 comments)."
        )
        rule = (
            "Rule (design/ai-review-findings.md): each finding is fixed "
            "(commit named in the thread) or rejected (one-line reason) "
            "before merge. This report only shows the state and any observed "
            "marker in the replies; it does not check that a fix or reason "
            "is real, and changes nothing."
        )
        lines += [
            head,
            "",
            rule,
            "",
            "| State | Started by | Anchor | File | Reply marker | First comment |",
            "|---|---|---|---|---|---|",
        ] + rows
        if more_threads:
            lines += ["", "Only the first 100 threads were read."]
    return "\n".join(lines) + "\n", counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    counts = {"unanswered": 0}
    failed = False
    try:
        token = os.environ["GITHUB_TOKEN"]
        threads, more = fetch(args.repo, args.pr, token)
        text, counts = summarize(threads, args.pr, more)
        try:
            head, reviews, more_rev = fetch_reviews(args.repo, args.pr, token)
            text += summarize_reviews(head, reviews, more_rev)
        except Exception as exc:  # noqa: BLE001 - second section also fails open
            text += (
                "\nReview bodies unavailable "
                f"({type(exc).__name__}). Nothing was changed.\n"
            )
    except Exception as exc:  # noqa: BLE001 - advisory report must fail open
        failed = True
        text = (
            f"### Review threads on #{args.pr} (informational)\n\n"
            f"Report unavailable ({type(exc).__name__}). Nothing was changed; "
            "this is not a check result.\n"
        )
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        try:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:
            pass  # advisory: an unwritable summary must not fail the run
    try:
        print(text)
    except OSError:
        pass
    if args.strict and (failed or counts["unanswered"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
