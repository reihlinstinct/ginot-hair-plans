# Plan-area source diagnostics

Issue #868. This is an **offline audit**, not a production correction. No
source values, snapshots, display fields, refresh logic or deadlines change.

## Policy

Compare `pl_area_dunam` with the **full plan geometry**, never the council
intersection area. The latter makes legitimate large/partial plans look like
unit errors. Full geometry must be explicitly EPSG:2039, valid and complete.
Even/odd ring composition preserves holes and nested islands; crossing rings
are unverified rather than automatically repaired.

The report retains `raw_pl_area_dunam` unchanged and adds a separate measured
area and quality label:

| Raw / full-geometry dunam ratio | Diagnostic |
| --- | --- |
| 0.95 to 1.05 | consistent_with_geometry |
| 900 to 1100 | suspected_square_metres_in_dunam_field |
| Other positive finite ratio | area_mismatch_review_required |
| Missing/invalid geometry | unverified_geometry |
| Missing/invalid raw area with usable geometry | invalid_or_missing_raw_area |

These thresholds are triage heuristics, not proof of intended source units.
They do not authorize dividing by 1000, replacing an official area or claiming
that the geometry is the legally controlling area. Small numerical differences
can reflect source versions, measurement methods or map generalization.
Unknowns are not clean results. The source file is never overwritten.

## Checked primary source, 16 November 2026

[Planning Administration ArcGIS layer](https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/xplan_without_77_78/MapServer/1),
read-only `/query`, individual `pl_number` predicates,
`returnGeometry=true`, `outSR=2039`. All returned parts were measured, without
clipping to the council. Only plan identifiers, raw area, Mavat URL and update
date were requested as attributes; no person-level fields.

| Plan | Raw field | Full geometry, dunam | Raw / measured | Diagnostic |
| --- | ---: | ---: | ---: | --- |
| 101-1336049 | 4105.0 | 4.104918 | 1000.02 | suspected square-metre value |
| 101-0055293 | 1.281 | 1.279752 | 1.0010 | consistent |
| 101-0092098 | 125942098.69 | 130074.766069 | 968.23 | suspected square-metre value |

The number **125942098.69 is present in the current snapshot and current
source for 101-0092098**, not 101-0055293. The older report attributed it to the
wrong plan. No historical disappearance or upstream correction was proved.

Official plan links returned by the source:

- [101-1336049](https://mavat.iplan.gov.il/SV4/1/1005381110/310)
- [101-0055293](https://mavat.iplan.gov.il/SV4/1/1000214629/310)
- [101-0092098](https://mavat.iplan.gov.il/SV4/1/1000240835/310)

These are case references, not evidence that plan instructions were read.
Primary plan-document confirmation of intended area units remains outstanding.
The ten snapshot raw/intersection ratios near 1000 are leads, not verified
unit errors, because intersection is not necessarily full plan area.

## Run without fetching or publishing

Save a complete, narrowly scoped ArcGIS response with `outSR=2039`, then:

```sh
python scripts/audit_plan_area.py --source /tmp/plan-query.json \
  --out /tmp/plan-area-diagnostics.json
```

Use a new output path. Wrong CRS, truncated responses, errors and an output
that already exists are rejected. This script is not wired into production.
A later change can expose reviewed diagnostics separately from raw display
values, but requires its own review and production approval. #868 remains open
for document confirmation and any adopted downstream policy.
