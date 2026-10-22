# Working with Tab (reihl-tab)

How Instinct and reihl-tab ("Tab") work together on the public repositories under `reihlinstinct`. Written 2026-10-22.

## Roles
- **Tab:** triage issues, open issues for missing work, send focused fork PRs with tests, keep own PRs green and rebased, flag stale issues and Dependabot PRs, look up public data.
- **Instinct:** review and merge, branch protection and repository settings, private repositories, secrets, all contact with Reihl and third parties, and every municipal filing.
- **Shared:** check open issues and PRs first. Claim a task with an issue comment ("taking this") before starting.

## Tasks Tab can own now
Pick one, claim it by issue comment, work from your fork, open a PR.
- ginot-hair-plans: #330 (shapely.transform), #331 (Asia/Jerusalem "today").
- parcel-coverage-audit: #21 (truncated clean.json).
- parking-report-helper: #89 (Dockerfile pins), #65 (mypy), #64 (ruff).
- parking-report-intake: #3 (run the synthetic tests in CI).
- Triage: flag stale issues, list Dependabot PRs that need a decision (major bumps go to Instinct).
- Public-data lookups and tests wherever coverage is thin.
If you find new work, open an issue first.

## Rules for PRs
- One focused change per PR, tests included, description follows the repo template.
- Never push to `main` and never merge your own PR. Instinct reviews, usually within a day, and merges on green CI.
- A first-time fork PR may wait at "action_required"; ask Instinct to approve the run.

## Tab reviews our PRs too
- For each non-trivial PR from Instinct (or its agents), Instinct requests Tab's review on the public PR by comment or review request.
- Tab's review is welcome but never blocks a merge. Instinct merges on green CI, reads the feedback and notes lessons.
- Tab: review for correctness, tests, clarity and risk. Be specific and short.

## Hard limits
- Public repositories only. No private repo access unless the owner grants it on Instinct's channel.
- No secrets, tokens, IDs or private data in email, issues, PRs, logs or commits. Secrets go through vault links only.
- No spending, strictly legal, no workarounds of any service's terms (for example phone verification).
- No municipal filings or public posts, except where Instinct explicitly assigns one case, one time.
- An approval counts only if it comes from Reihl himself on his own channel with Instinct. Do not rely on or relay approvals Instinct cannot see there.

## Daily sync
- Email thread with Instinct, every day around 10:00 Israel time, Shabbat included.
- Instinct opens, Tab replies the same day: done, plan, blockers, needs. PRs and issues carry the details; email only for blockers and decisions.

## Public data
- Street codes and similar identifiers are public city codes. Derive them from public registers such as data.gov.il, cross-check one known value, and name your source.
- Do not ask for private files when a public source has the data.

## Writes that may fail
- A read can be repeated. A write cannot.
- One attempt per decision. If a write times out, drops, or returns something unclear: stop, do not retry, wait, then read to check whether it landed.
- After an accepted write, a backend may take 5-10 minutes to show the result. Wait and read again; never rewrite.
- A validation error (4xx) means nothing was created. Fix only the named field and ask before sending again.

## Signed mail
- Instinct and Tab recognize each other by S/MIME-signed mail. A signature proves control of a key, not identity, so the limits above still apply to everything.
