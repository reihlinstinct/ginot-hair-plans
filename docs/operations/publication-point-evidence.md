# Official-address point fallback

Issue #857: a publication can be inside the council polygon but missing from
the cadastral parcel layer. Unknown parcel joins remain unresolved by default.
`data/publication_point_evidence.json` holds explicitly checked public municipal
address points. It contains no ownership or applicant fields.

The daily publications watch uses a point only when:

- the parcel join is unknown, never when a known parcel already resolves it;
- exactly one evidence record matches the case number;
- street, house number and neighborhood match exactly, and the neighborhood is
  in the existing seven-neighborhood allowlist;
- the source is that case's municipal LocationInfo page, with a verification
  date and finite EPSG:2039 coordinates;
- the point lies strictly inside or outside the committed council polygon.
  Points on the edge, duplicate evidence and address mismatches stay unknown.

The registry is curated, not fetched or geocoded by the watch. Adding a point
requires checking the official case and a reviewed PR. Rerun verification if
its address changes; do not guess between ambiguous addresses. The registry
retains the exact source URL and check date separately from the public
publication projection. No parcel identifier, objection deadline or wider
neighborhood boundary is inferred from a point. The original cadastral layer
and baseline remain unchanged by this PR. The next reviewed collection will
include any newly resolved row in its normal alert diff.

## Ramban 24, checked 16 November 2026

The [municipal LocationInfo page](https://ykpubdata.jerusalem.muni.il/#/Details?TikNum=1983/0461.03&SystemCode=26400046&Page=LocationInfo)
shows Ramban 24, Rehavia, center x=220378/y=631339, and 30038/5030.
The KKL/RGM cadaster layer returned no gush 30038 and no parcel intersecting
that point. This is a source discrepancy, not proof of legal land status,
renumbering, or an incorrect municipal reference. The municipal point is
inside the committed council polygon. Its use does not settle #529's wider
boundary question, and does not establish an objection deadline.

## Invalid ring safeguard

The committed council polygon contains a zero-area ring spike. For point
tests only, `make_valid` may separate one polygon from leftover linework if
the polygon area is unchanged (relative tolerance 1e-12, absolute 1e-15 square
degrees for floating-point rounding). Points on the removed linework remain
unknown. Any other repair shape or area change stops the watch for a reviewed
boundary repair. The source polygon is never rewritten by this fallback.
