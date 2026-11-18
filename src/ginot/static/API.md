# Public JSON API (v1)

The site publishes a static, read-only JSON contract under `api/v1/`
alongside the plan table. It is the supported way to consume the data
programmatically; `data.json` remains as a deprecated alias for one
release and will be removed in v2.

The data is a DRAFT/advisory mirror of official sources (mavat/iplan,
the municipality permit feed). It is never a legal determination:
derived objection deadlines are **estimates** (publication date + 60
days, and + 2 calendar months where the statutory rule applies), and
the authoritative document is always the linked official notice.

## Endpoints (GET only)

| Path | Contents |
| --- | --- |
| `api/v1/plans.json` | All tracked plan rows, public fields only |
| `api/v1/permits.json` | Tracked permit requests, public fields only |
| `api/v1/changes.json` | Recent plan status changes |
| `api/v1/meta.json` | `{"api_version": 1, "generated": "YYYY-MM-DD", "endpoints": [...]}` |

JSON Schemas live under `api/v1/schema/` (`plans.schema.json`,
`permits.schema.json`, `changes.schema.json`, `meta.schema.json`) and an
OpenAPI 3.1 description at `api/v1/openapi.json`. Changes within v1 are
additive only (new optional fields may appear); breaking changes ship
as `api/v2/` side by side.

## Field notes

- Dates are ISO `YYYY-MM-DD` strings (or `null`); the site's dd.mm.yy
  rendering is display-only.
- `station_desc` and `internet_short_status` carry the official Hebrew
  status names as published by the source.
- `objection_deadline_derived_60d_from_publication` and
  `objection_deadline_derived_2m_from_publication` are derived
  estimates; `deadline_source_note` (when present) explains the basis.
- Fields whose names start with `_` are internal and never appear in v1.

## Caching and rate expectations

Everything is a static file on the GitHub Pages CDN: fetch it at most
once per `meta.json` `generated` change (the site rebuilds on data
refreshes, typically daily). There is no authentication and no rate
limit beyond the CDN's; please cache aggressively.

## Examples

```sh
curl -s https://reihlinstinct.github.io/ginot-hair-plans/api/v1/plans.json \
  | jq '.[] | select(.advisory_urgent == true) | .pl_number'
```

```python
import json, urllib.request
meta = json.load(urllib.request.urlopen(
    "https://reihlinstinct.github.io/ginot-hair-plans/api/v1/meta.json"))
print(meta["api_version"], meta["generated"])
```
