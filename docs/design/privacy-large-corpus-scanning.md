# Fail-closed privacy scanning for the large public corpus (#860)

Design only. No enforcement change, scanner change, exemption, limit increase,
history rewrite, or source-document edit is authorized by this document. Each
implementation step is its own reviewed PR, shared scanner first, then one
real consumer, then any rollout.

## Corpus shape (measured at 70b9624, 2026-11)

- 1,057 tracked files, 797,496,751 bytes total.
- 797 UTF-8 non-NUL text files, 46,659,739 bytes; 5 files over 2 MiB.
- 260 binary or unparsed files (PDF, image, DWG and similar official-source
  documents) - unreviewed by any text triage.
- The reviewed shared scanner (`reihlinstinct/repo-checks`,
  `tools/privacy_scan.py`, see its `docs/PRIVACY_SCAN.md`) is bounded at
  20,000 files / 2 MiB per file / 32 MiB total / 15 s scan deadline. Run
  against this corpus it returns error (exit 2), not clean: both the per-file
  cap and the aggregate budget are exceeded. That fail-closed behavior is
  correct and stays.
- A separate bounded-by-snapshot direct text-pattern triage found 24
  candidate paths. That triage is preliminary: coordinates and vendor
  literals can resemble phone numbers, official-source documents can carry
  identifying data, and fixtures must be synthetically constructed before any
  verdict. Values stay out of this document and out of CI output.

## Design decisions

### 1. Large-corpus streaming mode in the shared scanner

A separate, explicitly selected mode in the shared trusted scanner - never a
silent relaxation of the default profile. The default profile
(2 MiB / 32 MiB / 15 s) is untouched; existing consumers keep it.

- Chunked streaming reads: fixed-size chunks (proposal: 256 KiB) with a
  carried overlap equal to the scanner's maximum token length (proposal:
  4 KiB). A candidate identifier that straddles a chunk boundary is seen
  whole exactly once; offsets are tracked so no match is double-counted and
  none is skipped.
- Overlong tokens fail closed: a single unbroken token longer than the
  overlap budget is an error for that file, never a silent skip.
- Hard caps remain, scaled for this corpus and fixed in scanner source:
  per-file 8 MiB, aggregate bytes-read 256 MiB, wall-clock scan deadline
  120 s, tracked-file ceiling 20,000. Any budget overrun is exit 2.
- Output stays counts-only: fixed category counts and coverage counts, no
  finding text, paths, values or digests on stdout/stderr.
- Protections carry over unchanged: tracked-inventory only, regular files
  only, root confinement, symlink/submodule/unresolved entries fail closed.

### 2. Explicit accounting for every tracked path

Every tracked path ends the run in exactly one bucket: `scanned_text`,
`unscanned_binary`, or `error`. `unscanned` is reported as unscanned, never
as clean.

- Binary classification reads a bounded prefix (proposal: 8 KiB) only; those
  bytes count toward the aggregate budget. No extension-only classification,
  no whole-directory bypass, no auto-baseline.
- A changed tracked inventory between listing and scan fails closed.
- The run summary is transport-free and complete: bucket counts must add up
  to the tracked file count, or the run errors.

### 3. Public-document review lane for binary content

The 260 binary paths (official-source PDFs, images, DWG) get a separate
review lane, outside the text scanner's scope.

- Official public availability does not override the CONTRIBUTING privacy
  rules; identifying data inside a public source document is still finding
  material.
- Source provenance is preserved privately where identifying.
- Ownership of source redaction and data regeneration is determined with the
  owner before any data file is edited. This design assigns no such edits.

### 4. Rollout: keep old guards until parity

1. Shared scanner large-corpus mode lands in `reihlinstinct/repo-checks`
   with its own review and tests.
2. A pinned, immutable-SHA consumer action runs it here in shadow mode while
   every existing guard stays required; normalized results must match the
   bounded triage expectations before anything is replaced.
3. Only then does the shadow mode become a required check, in its own PR.
4. The 24 preliminary candidate paths are triaged by hand against the
   synthetic-fixture rule before the shadow comparison, so parity compares
   like with like.

## Acceptance tests (for the implementation PRs)

- Size and time boundaries: per-file cap, aggregate budget, wall deadline,
  file-count ceiling - each exercised at, above and below the limit.
- Chunk-split matches: email, phone, ID and secret shapes placed across the
  chunk boundary and inside the overlap; exactly-once counting.
- Malformed and overlong tokens: fail closed, counted as errors.
- Symlinks, non-regular files, submodules, unresolved entries: fail closed.
- Giant binaries: bounded-prefix classification without full reads.
- Changed inventory between listing and scan: fail closed.
- Output: counts-only on stdout and stderr in every exit path; no matched
  values, paths or digests.
- Complete accounting: bucket counts sum to the tracked inventory.
- Targeted mutants of the above must die. Independent exact-head review and
  green CI on every PR.

## Explicit non-goals

No history rewrite, no deletion of source contacts or documents, no new
exemptions, no increase of the default scanner limits, no extension- or
directory-based bypass, and no blanket claim that the corpus is privacy-safe
as an outcome of this design.

## Open questions for the owner

1. Final budget numbers for the large-corpus mode (proposals above).
2. Ownership and sequencing of redaction/regeneration for any official-source
   document that triage confirms as identifying.
3. Whether the 5 text files over 2 MiB get a one-off manual review ahead of
   the shadow run.
