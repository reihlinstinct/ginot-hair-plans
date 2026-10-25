# Permit requests: default recency filter design (user instruction 2026-10-25)

## Status
Design draft for discussion before implementation (design-first rule, Tab
discussion pending). User instruction 2026-10-25: permit requests published
more than six months ago should NOT appear by default; they remain viewable
by changing the default date. No code changed by this document.

## Semantics (locked by the instruction)
- Date field: `publication_start` (s.149 publication start) ONLY - actual
  publication provenance, filled solely by the direct-scanner enrich path.
  Never `status_date`, application creation, or `details_checked_on`; the
  over.org.il mirror carries no publication dates at all.
- Rolling window: six calendar months, computed client-side at page load as
  today minus six months in the visitor's browser local timezone. No fixed
  date is baked into the build, the HTML, or the data.
- UI: a date input in the permits filter row, defaulting to the computed
  cutoff. Editing it re-filters (older requests become viewable); a reset
  restores the rolling default. This is the "change the default date" path
  the user asked for.

## Measured data cut (feed of 2026-10-25, cutoff 2026-04-25)
11,037 rows total. Default view today (non-terminal) = 4,229 rows.
- Dated (publication_start present): 1,011 rows = 694 terminal / 21 late /
  296 active. Inside the 6-month window: only 65 (64 active + 1 terminal).
  Older than the window: 946.
- Undated: 10,026 rows = 6,114 terminal / 3,187 late-stage / 725 active.

## Resolved semantic categories (the filter's world)
1. published-in-window (65 today): shown. (Future-dated starts count inside.)
2. published-older (946 today): hidden by default, recoverable via the date
   input. This is exactly the user's rule.
3. published-but-date-unknown (1,391 of all undated today; 73 active /
   75 late / 1,243 terminal): positive evidence of publication exists
   (status "תום תקופת פרסום" / "פורסמה בקשה להקלה" or a planned publication
   end) but no start date. NOT treated as old (nothing proves age) and NOT
   treated as never-published. Non-terminal rows shown by default with a
   visible "תאריך פרסום חסר" marker + live count.
4. no publication evidence in the current feed (8,635 of all undated today;
   652 active / 3,112 late / 4,871 terminal): a status-based classification
   ONLY - it does NOT prove the request was never published; historical
   publications may exist that our data does not carry. Kept explicit as
   uncertainty on the page, never hardened into a "legitimately no date"
   fact, and never lumped with "unknown recent publication". The user's
   rule does not target these: they stay under the existing status rules
   (active/late shown, terminal hidden), marked as date-unknown.
5. terminal / late-stage: existing default-hide rules unchanged; the
   categories above apply within every class, and terminal rows stay
   default-hidden regardless of category.

## What the numbers say about the options
- Filter with unknowns always visible (A): hides only 253 of 4,229 default
  rows today (6%) - declutter intent mostly fails while 91% are undated.
- Filter hiding all unknowns (B): default collapses to ~64 rows but wrongly
  hides 725 active requests, 652 of which are simply not published yet.
- Enrich-first correction (measured): the published-but-date-unknown
  set is 1,391 tiks overall (73 active) - the active slice is small. The
  no-evidence rows may simply lack publication in our data; enrich there
  would often CONFIRM absence (a real but negative result), not reveal dates. Enrich throughput honesty: one measured enrich
  window took 152 min (run 39380975772); per-tik rate is not directly
  measured, so no promise of "1-2 runs"; any enrich dispatch respects the
  existing runtime caps and 3s spacing.

## Minimal remaining user choice
Only category 3's default treatment for NON-terminal rows (73 active + 75
late today): show-with-marker (recommended, zero risk of hiding something
actionable) vs hide-with-count-badge. Everything else follows the
instruction or existing rules directly. Enrich of the evidence-tiks is a
small, independent improvement either way.

## Interaction with existing behavior
- shown(row) = (terminal rule) AND (category rule above). Search/status/sug
  filters unchanged. Rows already carry `data-pub` and the full set loads
  client-side (#169) - pure client-side filter in `_permits_section` +
  `docs/permits.html`; no scan/pipeline change.
- The undated/dated live count stays visible in the section header so the
  blind spot is explicit on the page; older rows always recoverable via the
  date input.

## Implementation sketch (after approval)
1. `_permits_section`: date input + reset + category markers/counts markup.
2. Page script: rolling cutoff on load (local tz), one predicate covering
   terminal + recency categories, invalid manual input falls back to the
   rolling default with a visible flag.
3. Tests: predicate unit tests per category incl. future date and invalid
   input; regression that 2026/0439.00 stays visible by default; desktop +
   mobile visual proof before merge.

## Coordination and scope
- PR #432 (spatial features + permit-case integration): orthogonal; any
  future permit-case cards apply the same default rule.
- Issues: #405 (permits page), #169 (client-side full row set).
- Out of scope: scan/enrich pipeline changes; statutory plans table
  untouched; only default display changes, nothing is unpublished.
- Visitor clock caveat: a wrong device date shifts the rolling window;
  documented in the page note, same trust model as the existing client-side
  deadline derivation.
