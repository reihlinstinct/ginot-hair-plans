# Plan search: orthographic normalization and the colloquial-name gap (#468)

> Status: design proposal, 2026-11-02. Implements the "design before code"
> step requested in #468. Data claims below were independently verified on
> 2026-11-02 (feed probe) and against main (code read).

## Current state (verified on main)

- Shared folding `_NORM_SEARCH_JS` in src/ginot/page.py (#413) is applied
  identically to the query and to each row's `data-search` text: lowercase;
  drops niqqud/cantillation, geresh/gershayim, ASCII and typographic
  quotes/primes, hyphens/dashes, invisible bidi/zero-width marks; collapses
  whitespace. The ג׳/ג'/ג’ variants from the issue are therefore already
  covered: "ג'ורג'" and "ג׳ורג׳" fold to the same string.
- Rows index `pl_number + pl_name` only.

## Verified feed reality (live probe 2026-11-02)

The issue hypothesized indexing street/address fields "when the feed
provides them". Probed the layer metadata
(`PlanningPublic/xplan_without_77_78/MapServer/1?f=pjson`): the service
exposes 50 fields (dates, status, quantities, geometry) and **none is a
street, address, or free-text location field**. There is no
`pl_location_text`. Conclusion: for the plans table there is no source
street field to index; that direction is moot.

## The residual gap is word-level, not character-level

The observed failure (owner query "קינג גורג" for plan 101-0617134,
"מלון המלכים - המלך ג'ורג' 60") cannot be closed by character folding:
"קינג" and "המלך" are different words. "קינג ג'ורג'" is the Hebrew
transliteration of the street's English name (King George); the official
Hebrew street name is "המלך ג'ורג'". Character normalization will never
bridge an English-derived colloquial name and an official Hebrew name.

## Options

- **A. Documented street-name alias pairs (recommended).** A small curated
  data file (e.g. `src/ginot/search_aliases.json`) of official-to-colloquial
  street-name pairs, each entry carrying a source citation, per the issue's
  rule "per-plan manual aliases only where a source documents the
  colloquial name". Alias expansion is applied symmetrically: both the
  query and the indexed text are folded, then alias-normalized. Seed entry:
  המלך ג'ורג' <-> קינג ג'ורג' (King George St.), with its source.
  Kept deliberately narrow: street names only, every entry cited, no
  free-form aliases.
- **B. Declare the observed case out of scope.** Close #468 after #413
  with the finding that the feed has no street fields and colloquial names
  are unmaintainable. Rejected: the owner hit this live on a flagship
  street; the issue already constrains aliases to documented ones, which
  keeps A maintainable.

## Regression tests (from the issue, for the implementation PR)

- Query "קינג גורג" finds the Kings Hotel plan row (101-0617134 when the
  plan is in the active set; test against a fixture row, not the live
  feed).
- ג׳/ג' variants of the same query find the same row.
- No false-positive explosion on short queries: alias expansion only
  applies to whole-token phrase matches, never single characters or
  substrings of longer words.
- Fixture row without a documented alias is unaffected.
