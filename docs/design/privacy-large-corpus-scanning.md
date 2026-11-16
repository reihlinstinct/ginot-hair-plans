# Fail-closed privacy scanning for the large public corpus (#860)

Design only. No enforcement change, scanner change, exemption, limit increase,
history rewrite, or source-document edit is authorized by this document. Each
implementation step is its own reviewed PR, shared scanner first, then one
real consumer, then any rollout.

## Corpus shape (measured at b090cd4, 2026-11-17)

- 1,169 tracked files, 634,278,763 bytes total.
- 918 UTF-8 non-NUL text files, 134,095,973 bytes; 10 files over 2 MiB, of
  which 7 are over 8 MiB: six localized `docs/**/permits.html` pages
  (14.6-16.0 MiB, growing with every feed batch) and
  `data/ginot_hair_parcels.geojson` (8.9 MiB).
- 251 binary or unparsed files (PDF, image, DWG and similar official-source
  documents) - unreviewed by any text triage.
- The reviewed shared scanner (`reihlinstinct/repo-checks`,
  `src/repo_checks/privacy.py`, see its `docs/PRIVACY_SCAN.md`) is bounded at
  20,000 files (`MAX_PATHS`) / 2 MiB per file (`MAX_FILE`) / 32 MiB total
  (`MAX_TOTAL`) / 15 s scan deadline, with a 30 s CLI `signal.alarm` and a
  10 s inventory-listing deadline (`MAX_INVENTORY` 4 MiB). Run against this
  corpus it returns error (exit 2), not clean: both the per-file cap and the
  aggregate budget are exceeded. That fail-closed behavior is correct and
  stays.
- A separate bounded-by-snapshot direct text-pattern triage found 24
  candidate paths. That triage is preliminary: coordinates and vendor
  literals can resemble phone numbers, official-source documents can carry
  identifying data, and fixtures must be synthetically constructed before any
  verdict. Values stay out of this document and out of CI output.
- Budget rule: every implementation PR re-measures the tracked tree with the
  scanner's own rule (NUL or invalid UTF-8 means binary) and re-checks the
  budgets below against it. The permit pages grow with each feed batch, so a
  budget that merely fits today is already wrong.

## Design decisions

### 1. Large-corpus streaming mode in the shared scanner

A separate, explicitly selected mode in the shared trusted scanner - never a
silent relaxation of the default profile. The default profile
(2 MiB / 32 MiB / 15 s) is untouched; existing consumers keep it.

- Chunked streaming reads: fixed-size chunks (proposal: 256 KiB) decoded with
  an incremental UTF-8 decoder, so a multibyte character split across a chunk
  boundary is held over and completed, never read as invalid. Each chunk is
  scanned with a carried overlap (proposal: 4 KiB) sized from the largest
  candidate span of the scanner's real patterns plus their lookbehind
  context: `EMAIL_CANDIDATE` (`[\w._%+@\-]+`, capped at 320 chars), `PHONE`
  and `ID` (one-character lookbehinds `(?<![\w+])`, `(?<![\w.\-])` plus
  separator runs), `UUID_TOKEN` (36 chars), `SECRET` (`TOKEN` prefixes and
  the single-line `KEY_HEADER`). The multi-line `KEY_BLOCK` in
  `secret_output.py` is a redaction pattern, not a detection pattern; this
  counts-only mode detects via `KEY_HEADER` and needs no multi-line state.
- Right-edge rule: the patterns also depend on what follows a candidate
  (greedy classes, the `(?!\w)` / `(?[\w\-]|\.\d)` lookaheads, the
  reserved-domain email check), so a candidate cut at the end of a window
  would be classified wrongly and produce spurious findings that move with
  chunk alignment as files change, breaking normalized parity. A match is
  accepted and its candidate evaluated only when it ends at least `overlap`
  bytes before the end of the window, or at end of file; anything later is
  deferred to the next window. Together with the lookbehind-sized overlap
  this replaces any separate double-counting rule: every byte range is
  evaluated under the same context as a whole-file scan, so per-file
  category sets match exactly.
- Overlong candidates fail closed: a single unbroken candidate of any
  pattern's class longer than the overlap budget is an error for that file,
  never a silent skip.
- Hard caps, sized from the measured tree with headroom and fixed in scanner
  source: per-file bytes-read 32 MiB (twice the largest tracked text file,
  bounding total bytes read per file across all chunks), aggregate
  bytes-read 512 MiB (about 3.8x the text corpus, including binary
  prefixes), wall-clock scan deadline 300 s, tracked-file ceiling 20,000.
  Any budget overrun is exit 2.
- Deadlines scale with the mode: the CLI `signal.alarm` is set to the mode's
  wall deadline (300 s, not the default 30 s), and the inventory-listing
  deadline scales to 30 s with `MAX_INVENTORY` unchanged (4 MiB holds the
  20,000-path ceiling). Without both, the 300 s wall limit is unreachable.
- Output stays counts-only: fixed category counts and coverage counts, no
  finding text, paths, values or digests on stdout/stderr.
- Protections carry over unchanged: tracked-inventory only, regular files
  only, root confinement, symlink/submodule/unresolved entries fail closed.

### 2. Explicit accounting for every tracked path

Every tracked path ends the run in exactly one bucket: `scanned_text`,
`unscanned_binary`, or `error`. `unscanned` is reported as unscanned, never
as clean.

- This mode changes one reviewed invariant on purpose: `PRIVACY_SCAN.md`
  says today "oversized binary files error; no prefix classification
  bypasses the limits." That rule is right for the default profile, but this
  corpus legitimately carries 9-16 MB UTF-8 text and 250+ official binaries
  that no text scan will ever cover, so the large-corpus mode replaces
  "oversized means error" with a defined `unscanned_binary` bucket that is
  accounted, compared against a reviewed list, and never counted as clean.
- Classification rule: read a bounded 8 KiB prefix (those bytes count toward
  the aggregate budget). A NUL in the prefix or an undecodable UTF-8 prefix
  means `unscanned_binary`. Otherwise the file streams as text under the
  incremental decoder. If invalid UTF-8 is found mid-file, the file is
  reclassified to `unscanned_binary` and its partial text results are
  discarded as scan coverage, but any finding counts already collected from
  the decoded prefix are kept (counts only): the file would be off-list in
  any case, and dropping collected evidence would weaken the gate. A NUL
  found anywhere in the stream, not only in the prefix, reclassifies the
  same way: NUL bytes are valid UTF-8, and the default profile calls any
  NUL-carrying file binary. A multibyte character cut by the 8 KiB prefix
  boundary is not 'undecodable': the prefix is decoded incrementally with
  the truncated tail held over. A text file with a NUL inside
  its first 8 KiB is `unscanned_binary` and skips text scanning. No
  extension-only classification, no whole-directory bypass, no
  auto-baseline.
- A changed tracked inventory between listing and scan fails closed.
- The run summary is transport-free and complete: bucket counts must add up
  to the tracked file count, or the run errors.
- Gate semantics for the unscanned bucket: the run exits 0 only when the
  error bucket is empty, every finding count is zero, AND the
  `unscanned_binary` set equals the reviewed owner-held list (section 3),
  keyed by path + Git blob id from `git ls-files -s`, so a changed binary
  under a listed path is drift, not a pass; no content leaves the runner.
  Findings exit 1. Budget overruns, inventory changes, and any unscanned
  entry missing from or added to the reviewed list exit 2, reported as
  counts only (how many entries are off-list, never which). These exit
  codes are the scanner's contract in every run; in shadow mode the
  workflow layer treats a non-zero exit as informational until the mode
  becomes a required check (section 4).

### 3. Public-document review lane for binary content

The 251 binary paths (official-source PDFs, images, DWG) get a separate
review lane, outside the text scanner's scope.

- Official public availability does not override the CONTRIBUTING privacy
  rules; identifying data inside a public source document is still finding
  material.
- Source provenance is preserved privately where identifying.
- Ownership of source redaction and data regeneration is determined with the
  owner before any data file is edited. This design assigns no such edits.
- The lane holds the reviewed, owner-approved list of expected
  `unscanned_binary` entries, keyed by path + blob id (section 2). Adding a
  new binary file, or replacing the content of a listed one, is a normal
  review event: the list entry changes in the same PR as the file, and any
  drift between the tree and the list fails the gate in section 2.

### 4. Rollout: keep old guards until parity

1. Shared scanner large-corpus mode lands in `reihlinstinct/repo-checks`
   with its own review and tests, budgets re-measured against the tree at
   that PR.
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
  chunk boundary and inside the overlap; a multibyte character split across
  the boundary decodes correctly; the right-edge rule holds at every chunk
  alignment, tested by sweeping the boundary across each pattern so no
  finding appears, disappears or changes with alignment.
- Malformed and overlong candidates: fail closed, counted as errors.
- Symlinks, non-regular files, submodules, unresolved entries: fail closed.
- Giant binaries: bounded-prefix classification without full reads; a file
  that turns non-UTF-8 or carries a NUL mid-stream is reclassified with its
  collected finding counts kept, not reported as scanned (no tracked file
  exercises this today, so a synthetic fixture is required).
- Changed inventory between listing and scan: fail closed.
- Output: counts-only on stdout and stderr in every exit path; no matched
  values, paths or digests.
- Complete accounting: bucket counts sum to the tracked inventory, and a
  binary entry whose path or blob id is not on the reviewed list fails the
  gate.
- Targeted mutants of the above must die. Independent exact-head review and
  green CI on every PR.

## Explicit non-goals

No history rewrite, no deletion of source contacts or documents, no new
exemptions, no increase of the default scanner limits, no extension- or
directory-based bypass, and no blanket claim that the corpus is privacy-safe
as an outcome of this design.

## Open questions for the owner

1. Final budget numbers for the large-corpus mode (proposals above, sized
   from the b090cd4 measurement with headroom).
2. Ownership and sequencing of redaction/regeneration for any official-source
   document that triage confirms as identifying.
3. Whether the 10 text files over 2 MiB (7 of them over 8 MiB) get a one-off
   manual review ahead of the shadow run.
