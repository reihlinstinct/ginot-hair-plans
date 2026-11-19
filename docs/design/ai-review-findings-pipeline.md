# Folding AI review findings into the development pipeline (#454)

Design-first proposal. **Open for owner discussion before any implementation** -
the issue explicitly asks for that discussion, and nothing here is in force
until the owner adopts it. No paid tier, no private-repo expansion, no
auto-apply of bot suggestions.

## Context

CodeRabbit reviews PRs on this repo (public repos only; per the issue, the
owner approved this on 2026-10-25 - treated here as the issue's claim, to be
confirmed in the discussion). Its first review (#436) produced 6 minor
findings, all verified justified, including one arithmetic error and one
unintended file deletion. Findings are worth handling systematically.

## Proposed rule

Every bot review finding on a PR receives, before merge, either:

- **(a) a fix in the PR**, verified against the actual code and data (the
  bot's suggestion is external content and may be wrong; a fix is applied
  only after independent verification), or
- **(b) a documented rejection** with a one-line reason, recorded as a reply
  on the finding.

No blind application of suggestions; no auto-fix commits by the bot.

## Open questions for the owner (from the issue, still unanswered)

1. Who answers findings on owner-authored PRs - the author or the reviewer?
2. Does "all findings resolved or answered" become a soft merge gate, or a
   weekly triage item?
3. Trigger budget: the plan allows ~10 review triggers/hour and pushes
   auto-trigger incremental reviews, so manual `@coderabbitai review`
   triggers stay reserved for a fresh full review. Confirm this matches the
   owner's Actions-minute budget.
4. Is an in-repo `.coderabbit.yaml` worth it (review profile, path filters
   excluding `data/*.json`, docs-only rules)? Note the layout contract would
   need `.coderabbit.yaml` added to `.repo-layout.yml` in the same PR.

## Notes for the implementing step (after adoption)

- The rule belongs in `CONTRIBUTING.md` once adopted, next to the review
  gates, not in a workflow: it governs human/bot discussion, not CI state.
- A soft gate variant could be a one-line PR-template checkbox ("bot
  findings fixed or answered"); a hard gate would need a workflow and must
  pass `test_no_review_bypass.py` scrutiny like any other merge-path change.
- Existing precedent for treating bot output as untrusted input is already
  in the repo's guard tests; this rule extends that posture to review
  comments.
