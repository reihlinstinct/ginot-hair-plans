# Unverified capabilities registry

Status: adopted for this repo in #680. The idea comes from the "unverified"
file in [OpenADLC](https://github.com/620legal/OpenADLC) (Apache-2.0, 620 Legal).
We read its documentation only. No code was copied and nothing from it is used.

## Why

Docs, PR bodies and agent reports sometimes describe something as working when
it was only designed, assumed or tested once. This registry lists every
capability we rely on that we have not proven, with the exact command that
would prove it. A claim leaves the list only with evidence.

## Rules

1. A capability we depend on but have not proven gets a row in **Unverified**
   before the PR that relies on it merges. Give it the next `U-NNN` ID.
2. Each row has a verification command someone else can run, and what a pass
   looks like.
3. A row moves to **Verified** only with the command's output, the date and a
   link to the issue or PR where it ran. Never delete rows. A claim keeps its `U-NNN` ID when it moves; never re-use an ID.
4. If a later change or failure disproves a verified row, move it back and open
   a `bug` issue with the evidence.
5. Reviewers check that PR claims match this registry. A PR must not state
   "works" for anything listed as unverified.
6. Verification that costs private-repo Actions minutes follows
   [actions-budget.md](actions-budget.md) first.

`tests/test_unverified_registry.py` checks the table format on every CI run.

## Unverified

| ID | Capability claim | Status | Verification command and pass condition | Last checked |
| --- | --- | --- | --- | --- |
| U-001 | The coverage gate fails CI when `enforce` is true and coverage is under the floor. | unverified: `enforce` is false, never exercised | `git switch -c verify-u001 && jq '. * {enforce:true, coverage_floor:100}' .github/qa-gates.json > /tmp/q.json && mv /tmp/q.json .github/qa-gates.json && git commit -am 'verify U-001 (do not merge)' && git push -u origin verify-u001 && gh pr create --draft --title 'verify U-001 (do not merge)' --body 'Throwaway, refs #680' && gh pr checks --watch`. Pass: the "Coverage gate" check fails. Then `gh pr close --delete-branch`. | never |
| U-002 | The macOS multiplier (10) in `.github/actions-budget.json` matches how the billing usage API reports minutes. | unverified: no private repo has used macOS this month | `GITHUB_TOKEN=... python3 scripts/ci/actions_budget.py --live --year Y --month M` in a month with a private macOS run. Pass: the macOS repo's minutes equal ten times its raw macOS minutes on the GitHub Billing and licensing usage page. | never |
| U-005 | The Windows multiplier (2) in `.github/actions-budget.json` matches how the billing usage API reports minutes. | unverified: no private repo has used Windows runners | Run `GITHUB_TOKEN=... python3 scripts/ci/actions_budget.py --live --year Y --month M` in a month with a private Windows run. Pass: the Windows repo's minutes equal twice its raw Windows minutes on the Billing usage page. Checked separately from U-002. | never |
| U-003 | The billing-API total reported by `actions_budget.py --live` agrees with the minutes GitHub's own Billing usage page shows for the same month. | unverified: the October reading (2,005 of 2,000) fits the private-repo Actions block of 2026-10-20 but was not compared with the Billing page | Run `GITHUB_TOKEN=... python3 scripts/ci/actions_budget.py --live --year Y --month M` for the current month and compare with Settings, Billing and licensing, Usage. Pass: the totals agree within 1 percent. | never |

## Verified

| ID | Capability claim | Evidence | Date |
| --- | --- | --- | --- |
| V-001 | The daily Mavat watch schedule fires unattended. | `gh run list --workflow mavat-watch.yml --event schedule --limit 3`: runs on 2026-10-29 and 2026-10-28 succeeded, the run on 2026-10-27 was cancelled. Partial: the cancelled run is not explained here. Ran for #680, run list: https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/mavat-watch.yml | 2026-10-29 |
| U-004 | Every workflow job that does not call a reusable workflow (`uses:`) has a job-level `timeout-minutes`, so no such job relies on GitHub's 360-minute default. | Fixed by #683 / PR #684 (merged as ef759cb). `python3 scripts/ci/actions_budget.py --check-timeouts` on this branch after merging main: exit 0, "0 job(s) without timeout-minutes". No workflow currently has a `uses:` job; the checker skips them by design because they cannot set a timeout, so a future one needs its own review. | 2026-10-29 |
