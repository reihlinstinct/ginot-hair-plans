# Permit requests: default recency filter design (user instruction 2026-10-25)

## Status
Design draft for discussion before implementation (design-first rule, Tab
discussion pending). User instruction 2026-10-25: permit requests published
more than six months ago should NOT appear by default; they remain viewable
by changing the default date. No code changed by this document.

## Semantics (locked by the instruction)
- Date field: `publication_start` (s.149 publication start) ONLY. Never
  `status_date`, application creation, or `details_checked_on`.
- Rolling window: six calendar months, computed client-side at page load as
  today minus six months in the visitor's browser local timezone. No fixed
  date is baked into the build, the HTML, or the data.
- UI: a date input in the permits filter row, defaulting to the computed
  cutoff. Editing it re-filters (older requests become viewable); a reset
  restores the rolling default. This is the "change the default date" path
  the user asked for.

## Load-bearing gap: missing publication dates (measured 2026-10-25)
Only 1,011 of 11,037 published rows (9%) currently carry `publication_start`.
The enrich backfill (s.149 dates for mirror-diff tiks) is shrinking this set
but is not complete. Rules:
- Rows without `publication_start` are NEVER hidden by the recency filter.
- No invented fallback date (not status_date, not first-seen, nothing).
- They render with a visible "ללא תאריך פרסום" marker, and the section header
  shows a live count of dated vs undated rows so the filter's blind spot is
  explicit on the page.

### Decision point for the discussion (recommendation A)
- A (recommended): unknown-date rows always visible + marker + header count.
  Zero risk of hiding something actionable; declutter effect limited until
  enrich coverage grows.
- B: unknowns hidden with the old ones, revealed by a separate toggle with a
  visible hidden-count badge. Better declutter, real risk of hiding an
  actionable request whose date we simply lack.
- C: unknowns in their own collapsed group with a count. Middle ground,
  more UI complexity.

## Interaction with existing behavior
- Terminal-status default-hide (#permits checkbox) stays independent:
  shown(row) = (terminal rule) AND (no publication_start OR
  publication_start >= cutoff). Search/status/sug filters unchanged.
- Rows already carry `data-pub` and the full set loads client-side (#169) -
  no data-pipeline or scan change. Pure client-side filter in
  `_permits_section` output + `docs/permits.html` script.
- Future-dated `publication_start` (observed, e.g. 2026-10-28) counts as
  inside the window.

## Implementation sketch (after approval)
1. `_permits_section`: add the date input + reset + markers/counts markup.
2. Page script: compute rolling cutoff on load (local tz), filter on
   `data-pub`, wire the input and the terminal checkbox through one
   predicate. Invalid manual input falls back to the rolling default and is
   flagged, never silently ignored.
3. Tests: predicate unit tests (dated-inside, dated-outside, unknown,
   terminal interplay, future date, invalid input); regression test that a
   currently-publishable tik (e.g. 2026/0439.00) stays visible by default;
   visual check desktop + mobile before merge (screenshot evidence).

## Coordination and scope
- Related: PR #432 (spatial features + permit-case integration design) -
  orthogonal; any permit-case cards it adds must apply the same default rule.
- Related issues: #405 (permits page), #169 (client-side full row set).
- Out of scope: scan/enrich pipeline changes; the statutory plans table is
  untouched; no change to what is published, only to default display.
- Visitor clock caveat: a wrong device date shifts the rolling window;
  documented in the page note, same trust model as the existing client-side
  deadline derivation.
