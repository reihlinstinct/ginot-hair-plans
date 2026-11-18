# Code style (#113)

The enforced standard is the tooling, not prose: `ruff.toml` (lint +
format) is the single source of truth and CI fails on any deviation. This
document records the rules the tooling cannot express. Where this file and
`ruff.toml` disagree, `ruff.toml` wins and this file gets fixed.

## Python

- Lint/format: `ruff check` + `ruff format` with the repo's `ruff.toml`
  (same version as CI's `RUFF_VERSION`; `.pre-commit-config.yaml` pins it
  locally). The C901=10 / PLR0915=50 complexity ratchet (#111) and the S
  security triage (#112) are part of the standard: new and touched code
  stays under the limits, and per-file-ignores entries only shrink.
- Naming: `snake_case` functions and variables, `UPPER_SNAKE` module
  constants, no abbreviations that are not domain terms (`tik`, `gush`,
  `helka` are domain terms).
- Errors: fail closed. A check that cannot run is an error, never a pass
  (see the checkpoint lifecycle gate, #566). Broad `except Exception` is
  allowed only where a test asserts the resilience contract, and then
  carries a `# noqa: BLE001` with the reason and the counting/diagnostics
  path (#399 is the pattern).
- Logging/diagnostics: print counts and identifiers, never secrets,
  tokens, cookies or matched private values. Scanner-style tools emit
  counts-only output on every exit path (#860 design).
- No secrets in code, tests, fixtures or docs. Synthetic fixtures only;
  nothing captured from live traffic is committed.
- Subprocess: explicit argument lists, never `shell=True`; partial paths
  only where the S607 triage already grandfathered them.

## Tests

- Every test file opens with a module docstring saying what it guards, and
  groups tests under `# Section:` headers.
- One behavior per test; fixtures are synthetic and small.
- A fix ships with a regression test; a feature with end-to-end fixtures at
  known coordinates/values plus, for UI, visual verification in both
  browser engines.
- Browser (Playwright) tests stay quarantined from the unit suite; a flake
  is a bug to fix, not a retry to add.

## Repo-specific gates

- Signed commits; branch from `origin/main`; merge by merge commit on green
  CI at the exact head.
- `docs/` is regenerated with `scripts/ci/check_docs_fresh.py --write`
  after any `src/ginot/page*.py` or `static/` change; the freshness gate is
  the sync check.
- New files must satisfy `.repo-layout.yml`; update the contract in the
  same PR as the file that needs it.
- Workflows: actions pinned by full-length digest with the version in a
  comment; no local clock times in workflow comments (UTC only); merge-path
  changes must pass `test_no_review_bypass.py`.

## Web assets

- CSS and JS live in static files under `src/ginot/static/`, not Python
  string literals (page.py's embedded blobs are grandfathered; new assets
  go to files, and moving the legacy blobs out is the #113 follow-up).
- No client-side computation that a build step can do; heavy derived data
  ships precomputed and lazy-loaded.

## Scripts vs src

Reusable logic belongs in `src/ginot` (tested, packaged); `scripts/` holds
entrypoints and CI glue. Duplicated helpers are moved into `src/ginot` as
they are touched, with their tests, not copy-pasted again (#113 follow-up:
`land_feed.py`, `vpn_watch.py` first, by measured coverage).
