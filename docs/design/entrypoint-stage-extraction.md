# Staged extraction of Mavat and permit-feed entrypoint stages (#839)

Design only. No refactor is authorized by this document. Each extraction step
is its own reviewed PR with synthetic fixtures and killed mutants; no VPN,
live fetch, live run or publication is ever refactor validation. Independent
exact-head review and fresh green CI on every PR.

## Current state (measured at d2da494, 2026-11-18)

- `scripts/vpn/permit_feed.py` (781 lines): `main()` was a single 70-statement
  function of complexity 21 until #111 split it into stage helpers
  (`_parse_args`, `_load_council_parcels`, `_resolve_batch`, `_load_previous`,
  `_checkpoint_gate`, `_resume`, `_scan_batch` with `_parcel_rows` and
  `_scan_parcel`, `_fetch_details` with `_fetch_one_detail`, `_merge_previous`,
  `_write_feed`). `main()` is now a short orchestrator. This is the shape this
  design generalizes; the remaining seam is that the stages still call
  module-level effects directly (`time.sleep`, `call()`, checkpoint pushes).
- `scripts/vpn/mavat_docs.py` (1,207 lines): `main()` is 575 statements with
  cyclomatic complexity 160 (ruff C901/PLR0915, grandfathered in `ruff.toml`
  per the #111 ratchet). Browser automation, discovery, download and storage
  interleave in one body, with a nested `harvest_token` closure (complexity
  12) capturing mutable lists.
- Both entrypoints sit above the C901=10 / PLR0915=50 ratchet from #111;
  `mavat_docs.main` is the largest remaining violator in the repo.

## Stage decomposition

### permit_feed.py (finish what #111 started)

1. **Inject boundaries**: `sleep`, the API `call` function, and the
   checkpoint `push` become parameters with production defaults
   (`def _scan_batch(..., sleep=time.sleep, api_call=call, push=push_checkpoint)`).
   Tests stop monkeypatching module globals and pass fakes; the run_feed
   harness keeps its current surface.
2. **Stable diagnostics**: `_STATS` and `_LAST_CHECKPOINT` move behind a
   small `RunDiagnostics` object created in `main()` and passed down; the
   printed summary lines keep their exact current wording (tests assert on
   them).
3. **Output compatibility**: the feed JSON schema, the checkpoint branch
   layout and the provenance file are frozen by existing tests
   (`test_permit_feed_pipeline.py`, `test_checkpoint_lifecycle.py`); any PR
   that changes a byte of them is a data change, not this refactor.

### mavat_docs.py (the real target)

Decompose `main()` along the seams its own comments already draw:

1. **Browser stage**: playwright lifecycle (context, page, navigation) behind
   a `MavatSession` context manager; injected `sync_playwright` factory so
   tests run against a fake page.
2. **Discovery stage**: accordion expansion and request listening
   (`harvest_token` becomes a pure collector returning tokens/links, no
   closure over outer lists).
3. **Download stage**: ZIP/document fetching given a discovered URL list;
   injected `fetch` so no network in tests.
4. **Storage stage**: writing `data/mavat_docs.json` and the document tree;
   takes plain records, returns the written paths. Output bytes and filenames
   frozen by fixture comparison.
5. `main()` becomes an orchestrator under the ratchet limits, same CLI flags,
   same exit codes, same printed diagnostics (wording frozen by tests).

## Cross-cutting rules

- **Order**: shared helpers first (none expected to be shareable beyond
  diagnostics patterns), then `permit_feed` injection seams (smallest), then
  `mavat_docs` one stage per PR in the order above.
- **Fixtures**: synthetic API pages for permit_feed (existing pattern in
  `test_permit_feed_pipeline.py`), a recorded fake Mavat page for the browser
  stage, synthetic ZIP bytes for the download stage. No captured live traffic
  is committed.
- **Mutants**: for each extracted stage, at least one targeted mutant
  (swapped boundary, dropped deferral, wrong exit code) must be shown to die
  against the new tests.
- **Ratchet**: when a stage lands, its `ruff.toml` per-file-ignores entry
  shrinks or disappears in the same PR; entries never grow.
- **Behavior preservation**: identical CLI surface, identical stdout/stderr
  wording, identical output bytes, identical exit codes. A PR that cannot
  show this parity on the synthetic fixtures does not merge.

## Non-goals

No workflow changes, no new municipal requests, no cadence changes, no
publication of Mavat artifacts, and no weakening of the anti-bot stop
conditions (exit 2 paths) in either entrypoint.

## Open questions

1. Does `mavat_docs` keep its token-harvest retry budget exactly as-is, or
   may the browser stage expose it as a parameter (default unchanged)?
2. Should `RunDiagnostics` in permit_feed also absorb the ad-hoc
   `failures` counter in `_scan_batch`, or stay limited to `_STATS` /
   `_LAST_CHECKPOINT`?
