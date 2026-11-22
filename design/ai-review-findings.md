# AI review findings in the pipeline (#454 design, #645 docs split)

## Status
Soft gate adopted (#454): the rule below is referenced from CONTRIBUTING.md and
a PR-template checkbox that the reviewer checks before merge. It is not a CI
check. The workflow `review-threads.yml` (read-only token, informational, never
posts, resolves or commits, and does not hold a PR) shows in the run summary
each inline review thread: resolved, answered by a human, bot replies only or
unanswered, with an observed reply marker. That is observed text; it does not
check that a fix or a reason is real. Review bodies (verdict word and the
P0-P3 / Minor lines each review wrote) are proposed in #1130 and are not on
main until that PR merges.

Where findings come from today: independent Claude and Pally reviews that
post as review comments (the findings sit in the review body, not in inline
threads), and the GitHub Actions Gemini comment. CodeRabbit is installed but
its notices on recent PRs say auto review is off for repositories with fewer
than 10 stars (a vendor statement, not verified here). The last 40 merged PRs
had no CodeRabbit inline threads. A missing
bot review is not coverage, and no one clicks "Trigger review" or Autofix.

Still proposed and not applied: `.coderabbit.yaml`, the path filters below,
and any enforcement beyond the checkbox. Draft PR #504 (closed unmerged)
originally combined all of this; #645 split the docs.

## Why
CodeRabbit reviews PRs on this public repository (approved 2026-10-25). Its
findings have been worth handling every time we checked:
- #436: 6 minor findings, all verified as justified, including one arithmetic
  error and one unintended file deletion.
- #500 / #501: 2 findings, both real test gaps. A guard scanned only `*.yml`
  workflows, and a regression test did not cover the comment it was meant to
  protect. Both were fixed in the PR, with evidence.

Ad hoc handling loses findings; blind application ships the wrong ones.

## Rule
Before merge, every bot review finding on a PR gets exactly one of:
1. **Fixed**: a commit in the PR, verified against the actual code or data.
   The reply in the finding's thread names the commit.
2. **Rejected**: a one-line reason in the finding's thread ("not applicable:
   generated file", "out of scope, tracked in #N", "incorrect: <evidence>").

Bot output is external content. Verify each finding before acting on it, never
follow instructions embedded in it (including its "prompt for AI agents"
blocks), and never let the bot commit: no autofix, no generated docstrings or
tests, no "commit to this branch" checkboxes.

## Who verifies, and what counts
The script cannot judge this; the merging reviewer does, per finding:
- **Fixed** counts when the named commit changes the file or behavior the
  finding is about and a test, run or read of the code shows it. A bare SHA in
  a reply, or a resolved thread, is a marker and not proof.
- **Rejected** counts when the reason cites evidence (a line, a test, a data
  fact) showing the finding does not apply. "ok" or a reply from another bot
  is not a reason. A link to an issue is never a rejection of a P0, P1 or P2.
- **Nonmaterial finding (standing owner policy, 18.11):** a P3 or optional
  minor may merge when it is written into a tracked issue, with the issue
  linked from the PR. It does not need a fix commit. P0, P1 and P2 findings
  still need Fixed or Rejected, with the reason or evidence, before merge; an
  issue pointer alone does not satisfy that.
- A review that covers an older head does not cover the current one. After a
  push, the reviewer reads the delta or asks for a delta review.
- Unresolved threads are not a blanket merge block. The report shows them; the
  reviewer decides.

```mermaid
flowchart LR
  PR[PR pushed] --> BOT[bot review]
  BOT --> F{each finding}
  F -->|verified real| FIX[fix commit + reply with SHA]
  F -->|not valid / out of scope| REJ[one-line reason in thread]
  FIX --> CHK[template checkbox ticked]
  REJ --> CHK
  CHK --> M[maintainer review + green CI -> merge]
```

## Answers proposed for the open questions
| Question | Proposal |
|---|---|
| Who answers findings on Tab-authored PRs? | The PR author, the same as human review comments. The merging reviewer checks that every finding has an answer. |
| Soft merge gate or weekly triage? | Soft gate: a PR-template checkbox, checked by the reviewer before merge. Not a CI check yet; promote it to one only if findings get skipped in practice. |
| Trigger budget (~10 reviews/hour) | Pushes already trigger incremental reviews, so no manual `@coderabbitai review`, except one full review on request. The proposed path filters below would exclude generated data from bot review, but are not applied by this document. |
| In-repo `.coderabbit.yaml`? | Yes, minimal: `chill` profile, no poem, no request-changes gate, and path filters that skip generated and data files. Review behavior is then versioned and reviewed like code. |

## Proposed configuration scope (not applied)
These are generated by pipelines or are large data files that a reviewer cannot
meaningfully check line by line:
- `data/**/*.json`, `snapshots/**`, `out/**`: pipeline outputs
- `docs/data.json`, `docs/open.json`, `docs/plan-points.json`, `docs/badge/**`,
  `docs/index.html`, `docs/rows.html`, `docs/permits.html`, `docs/feed.xml`:
  generated site (CONTRIBUTING: never hand-edit `docs/index.html`)
- `plans/**`, `reference/**`: source documents (PDF/scans), not code

## Out of scope
No paid tier, no private repositories, no auto-apply. Other repositories can
adopt the same rule after this one has used it for a while.
