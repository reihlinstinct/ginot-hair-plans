# Actions minute budget: stop and ask

Status: adopted for this repo in #680. The per-task and per-month cap idea comes
from [OpenADLC](https://github.com/620legal/OpenADLC) (Apache-2.0, 620 Legal).
We read its documentation only. No code was copied.

## Why

The owner's policy is to stay within 2,000 private-repo Actions minutes a month
(the free-plan allowance as the owner understands it; GitHub may express included
usage as a dollar amount, so the reporter's minute total is not a check against
actual charges, see U-003 in the [registry](unverified-capabilities.md)). This
repo is public, so its own runs are free, but the same owner's private repos
share the cap. The project must stay free, so a cap that is crossed means stop
and ask, not carry on.

## Caps

All values live in `.github/actions-budget.json`. Only the owner raises them.

| Cap | Value | What happens |
| --- | --- | --- |
| Monthly private-repo minutes | 2,000 (owner policy) | At 50 percent: warn in the weekly triage. At 80 percent (1,600): **stop** starting private-repo runs and ask the owner. |
| Per task | 60 runner-minutes | Estimate before starting a task that dispatches workflows (sum of jobs, matrix included). Over 60: ask first. |
| Per job | `timeout-minutes` on every job | A job without one uses GitHub's default of 360 minutes, so set it explicitly. Verified as U-004 (2026-10-29, #684) in the [registry](unverified-capabilities.md). |

Public-repo minutes are not counted in the monthly cap. Visibility is read today, not for the billing month: the reporter prints the minutes of repos that are not private now, so a repo that changed visibility this month is visible and can be counted by hand.

## Checking the numbers

Read-only, uses the billing usage API (current month; pass another `--year` and `--month` for a past one):

```
GITHUB_TOKEN=... python3 scripts/ci/actions_budget.py --live --year $(date -u +%Y) --month $(date -u +%-m)
python3 scripts/ci/actions_budget.py --check-timeouts
```

The token needs read access to the account's billing usage and private repos.
Exit code 2 means the stop threshold is crossed, 3 means jobs without a timeout.
The script does not block anything by itself. The stop rule is a process rule
for agents and maintainers until the owner decides on CI enforcement.

## Stop-and-ask procedure

1. Run the check before dispatching any workflow in a private repo, and in the
   weekly triage.
2. At **warn**: say so in the triage summary and prefer running tests locally.
3. At **stop**, or when a task estimate is over the per-task cap: do not start
   the run. Tell the owner the current figure, the task and the estimate, and
   wait for an explicit yes.
4. If a run is already in progress when the cap is crossed, let it finish unless
   it is runaway, and report.

## Not in scope here

- No workflow, setting or secret changes.
- No automatic enforcement in CI. That needs an owner decision and a place for
  the token to live.
