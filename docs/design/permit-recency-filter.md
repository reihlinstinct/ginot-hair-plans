# Permit requests: default recency filter design (user instruction 2026-10-25)

> REVIEW SUMMARY (current semantics, this commit, 2026-10-25 07:30 IDT,
> design review closed - Tab review 2026-10-25 incorporated, all its data
> claims independently recomputed and confirmed)
> Locked by user instruction: filter on `publication_start` ONLY; rolling 6
> calendar months in the visitor's browser local timezone; older recoverable
> by editing the default date input; terminal default-hide unchanged;
> pure client-side, no heavier site, no new assets; mobile checked before merge.
> Categories (counts from 2026-10-25 feed; total vs default-visible under
> the adopted option A): 1 published-in-window 65 total / 64 default-visible;
> 2 published-older 946 total / 0 default-visible (253 non-terminal rows
> recoverable via the date input); 3 published-but-date-unknown 1,391 total /
> 148 default-visible (73 active + 75 late); 4 no-publication-evidence 8,635
> total / 3,764 default-visible (652 active + 3,112 late) (status-based only,
> NOT proof of never-published) - shown under existing rules, marked
> date-unknown;
> 5 terminal/late rules unchanged.
> RESOLVED decision (was the only meaning-changing one): category-3
> non-terminal default = A show-with-marker, ADOPTED. Rationale (Tab review,
> verified): 92.5% of the 4,229 visible rows have no publication date and
> that absence concentrates in one legitimate stage (draft permit prepared:
> 2,672 of 2,692 undated) - hiding undated rows hides requests that have not
> reached a publication milestone, which is not recency; B's ~64-row default
> would misrepresent a live pipeline on a civic-visibility page; C adds UI
> state for no gain over A. Refinement adopted with A: the date-unknown
> marker/counter is SPLIT per epistemic state - category 3 (known published,
> date unknown) and category 4 (no publication evidence) get separate
> counters, never one flattened number.
> Enrich note: no "unknowns collapse" promise - enrich mostly confirms absence
> for category 4; one measured enrich window 152 min, per-tik rate unmeasured.
> No implementation before the discussion closes.

## Status
Design discussion CLOSED 2026-10-25 (decision recorded below); implemented
in #448 and live. User instruction 2026-10-25: permit requests published
more than six months ago should NOT appear by default; they remain viewable
by changing the default date. This document records the design; it changes
no code itself.

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
   75 late / 1,243 terminal): positive evidence the request entered the
   publication STAGE exists (status "תום תקופת פרסום" / "פורסמה בקשה להקלה"
   or a planned publication end) but no start date. A planned end alone is
   evidence of a scheduled window, not proof a publication completed - see
   the Decision section. NOT treated as old (nothing proves age) and NOT
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
  rows today (6%) - declutter intent mostly fails while 92.5% are undated.
- Filter hiding all unknowns (B): default collapses to ~64 rows but wrongly
  hides 725 active requests, 652 of which are simply not published yet.
- Enrich-first correction (measured): the published-but-date-unknown
  set is 1,391 tiks overall (73 active) - the active slice is small. The
  no-evidence rows may simply lack publication in our data; enrich there
  would often CONFIRM absence (a real but negative result), not reveal dates. Enrich throughput honesty: one measured enrich
  window took 152 min (run 39380975772); per-tik rate is not directly
  measured, so no promise of "1-2 runs"; any enrich dispatch respects the
  existing runtime caps and 3s spacing.

## Decision (resolved by design discussion 2026-10-25)
Category 3 default treatment for NON-terminal rows: **A - show with marker**,
per the recommendation above and the design review's verified quantified
reasoning (92.5% of visible rows undated, concentrated in the draft-permit
stage; B would misrepresent pipeline activity; C rejected as extra UI state).
No user schema question remains; everything else follows the instruction or
existing rules. Adopted refinement: the date-unknown counter splits
category 3 (published, date unknown) from category 4 (no publication
evidence) - two labels, two counts. Enrich of the evidence-tiks is a small,
independent improvement either way. No fallback date field exists in the
current feed (verified): `status_date` is 0/11,037 populated today;
`publication_end_planned` (1,749 rows, 1,388 without a start) is an
independent estimate, not a publication proxy - A with clear marking is the
honest option.

## Interaction with existing behavior
- shown(row) = (terminal rule) AND (category rule above). Search/status/sug
  filters unchanged. Rows already carry `data-pub` and the full set loads
  client-side (#169) - pure client-side filter in `_permits_section` +
  `docs/permits.html`; no scan/pipeline change.
- The undated/dated live counts (split per category 3 vs 4) stay visible in
  the section header so the blind spot is explicit on the page. Unlike the
  `refill()`/closed-count pattern (which counts all loaded rows), the split
  counters count only rows matching the CURRENT filter set (the `match()`
  result): they recompute on EVERY filter change - search, status, sug,
  dates, terminal toggle - not only on the recency toggle; older rows
  always recoverable via the date input.
- DST: the window boundary is computed at a specific instant in the
  visitor's local timezone; day-granularity DST drift is accepted as a
  known, documented limitation (same trust model as the existing client-side
  deadline derivation and the `?today=` debug override).

## Implementation sketch (after approval)
1. `_permits_section`: date input + reset + category markers/counts markup.
2. Page script: rolling cutoff on load (local tz), one predicate covering
   terminal + recency categories, invalid manual input falls back to the
   rolling default with a visible flag.
3. Tests: predicate unit tests per category incl. future date (real case
   in feed: 2026-10-28), malformed/partial `publication_start` (defensive
   parser - the field is scraper-sourced and could regress), and an explicit
   month-end rolling-subtraction case (Aug 31 -> Feb class, the classic
   setMonth overflow) - expected outcome: subtraction CLAMPS to the last
   day of the target month (Aug 31 rolls to Feb 28, never Mar 3); a
   malformed or partial `publication_start` is treated as NO date: the row
   stays visible as date-unknown under option A and never gets a bogus
   date; regression that 2026/0439.00 stays visible by default
   PLUS a category-4 undated-active fixture (e.g. a draft-prepared row) that
   must stay visible under A - 0439.00 is dated (2026-10-18, category 1) and
   does not exercise the undated decision on its own; desktop + mobile
   visual proof before merge, including the 6th filter-row control fitting
   without wrapping on a narrow viewport.

## Coordination and scope
- PR #432 (spatial features + permit-case integration): orthogonal; any
  future permit-case cards apply the same default rule.
- Issues: #405 (permits page), #169 (client-side full row set).
- Out of scope: scan/enrich pipeline changes; statutory plans table
  untouched; only default display changes, nothing is unpublished.
- Pre-existing, unrelated follow-up surfaced by review: `docs/permits.html`
  (8.1 MB, all 11,037 rows) is fetched unconditionally on every page load
  (`page.py` unconditional `fetch('permits.html')`); this filter saves no
  network weight. Deferred-fetch follow-up tracked in its own issue.
- Visitor clock caveat: a wrong device date shifts the rolling window;
  documented in the page note, same trust model as the existing client-side
  deadline derivation.
