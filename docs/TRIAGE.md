# Labels, triage, and working targets

This repo is public. Never put personal data (names, phone numbers, בעלי עניין fields) in issues, PRs, or comments.

## Label set

| Label | Kind | Use |
| --- | --- | --- |
| `bug` | type | A failed run, wrong data, or tooling defect |
| `enhancement` | type | New work or improvement |
| `analysis` | area | Analysis features and investigation |
| `data-source` | area | Data acquisition (permit API, iplan, land.gov.il, over.org.il mirror) |
| `workflow` | area | GitHub Actions workflows / automation |
| `documentation` | type | Docs |
| `needs-triage` | status | New issue awaiting triage |
| `blocked` | status | Blocked on an external dependency or decision |
| `needs-user` | status | Needs a decision or input from the user |
| `priority:high` | priority | Do soon |
| `priority:low` | priority | Do when convenient (no label = normal) |

## Triage flow

1. New issues arrive with `needs-triage` (issue templates apply it automatically).
2. Triage: add type + area labels, set priority if not normal, assign a milestone (see below), remove `needs-triage`.
3. `blocked` / `needs-user` mark issues that cannot move without something outside the repo.

## Working target dates

Milestones carry the working target date for their issues (M1: 2026-10-22, M2: 2026-10-28, M3: 2026-11-04). A target date is a **working target for planning, not a commitment**; it moves with the pipeline. Each issue with a milestone gets a comment stating its working target.

## Bug policy

Whenever a bug is detected (failed run, wrong data, tooling defect), open a `bug` + `needs-triage` issue with:

- evidence: run URLs, log excerpts, data samples,
- impact and suspected fix when known,
- a working target date (milestone).

The fixing PR links the issue (`fixes #N`).
