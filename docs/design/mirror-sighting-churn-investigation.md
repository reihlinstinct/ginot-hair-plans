# Mirror ingest: sighting-only churn investigation (#820)

Investigation only - no sighting-date semantics changed. Question from #820:
`#819` derives a content marker and reuses `generated` when records are
identical; can sighting-only changes still alter content, and is daily
`last_seen` churn established? Measured against the repo's own committed
ingest history (`data/permit_mirror.json`, 14 consecutive ingest pairs,
2026-10-20 to 2026-11-16, 172,332 same-tik row pairs).

## Method

For each consecutive ingest pair, per tik present in both: the changed-field
set, then split into "only sighting fields changed"
(`mirror_first_seen`, `mirror_last_seen`, `mirror_sample_date` - the three
fields the comparison ignores) vs "other content changed", with a histogram
of which other fields changed.

## Findings

- 172,221 of 172,332 row pairs (99.94%) changed ONLY the three sighting
  fields. Daily `last_seen` churn is therefore established at the row level:
  nearly every row's `mirror_last_seen` moves on every ingest.
- 111 row pairs (0.064%) changed other content, and they are real lifecycle
  updates, not sighting artifacts:
  - `status` + `status_date`: 70 transitions (the dominant class - source
    status progression);
  - `status_date` alone: 3; `sugbakasha`: 3; `mahut`: 3; `address`: 2;
    mixed small sets: the rest;
  - one cluster of 18 `publication_start`/`publication_end_planned` changes
    on 2026-10-26 to 27 matches the enrichment-preservation fix (#490).
- No row pair showed a non-sighting content change attributable to a
  sighting event. In this window, "otherwise identical except sighting
  fields" and "content unchanged" were the same set.

## Conclusion for #819

Ignoring the three `mirror_*` fields when deciding whether a record is
unchanged loses no observation evidence in measured history: content changes
arrive through the source's own fields (status, dates, address) and are
exactly the changes the marker must catch - and does. The sighting fields
themselves are preserved across re-ingests (earliest first_seen / latest
last_seen, #794), so observation evidence is retained in the mirror file
even when the derived marker is reused.

Recommendation: keep current sighting-date semantics and the #819 marker
derivation. Re-run this comparison after any ingest source change or after
a month of daily ingests to confirm the 0.064% rate holds.

## Reproduction

Committed snapshots come from `git log -- data/permit_mirror.json`; the
comparison loads each version with `git show <sha>:data/permit_mirror.json`,
joins on `tik_num` and computes changed-field sets as above. Pure standard
library; no live fetch.
