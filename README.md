# ginot-hair-plans

<!-- Live public counters: generated static endpoint JSON, no scan triggered. -->
[![published range](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fparcel-progress.json&cacheSeconds=300)](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/permit-feed.yml)
[![remaining](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fparcel-remaining.json&cacheSeconds=300)](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/permit-feed.yml)
[![Python suite](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Freihlinstinct%2Fginot-hair-plans%2Fbadge-data%2Ftests.json&cacheSeconds=300)](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/ci.yml)
[![test coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Freihlinstinct%2Fginot-hair-plans%2Fbadge-data%2Fcoverage.json&cacheSeconds=300)](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/ci.yml)
[![latest release](https://img.shields.io/github/v/release/reihlinstinct/ginot-hair-plans)](https://github.com/reihlinstinct/ginot-hair-plans/releases)

Range badges show published cursor progress, not verified query success. Tests/coverage show the last successful main Python 3.12 suite (browser and worker jobs are separate). Shields may cache for five minutes.

[![CI](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/ci.yml/badge.svg)](https://github.com/reihlinstinct/ginot-hair-plans/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![last commit](https://img.shields.io/github/last-commit/reihlinstinct/ginot-hair-plans)](https://github.com/reihlinstinct/ginot-hair-plans/commits/main)
[![plans](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fplans.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![updated](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fupdated.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![page](https://img.shields.io/badge/page-live-blue)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![אישור](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_approved.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![בבדיקה תכנונית](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_review.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![במילוי תנאים להפקדה](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_conditions.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![הפקדה להתנגדויות](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_deposit.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![הכרעה](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_decision.json)](https://reihlinstinct.github.io/ginot-hair-plans/)
[![בהליך אישור](https://img.shields.io/endpoint?url=https%3A%2F%2Freihlinstinct.github.io%2Fginot-hair-plans%2Fbadge%2Fstatus_inproc.json)](https://reihlinstinct.github.io/ginot-hair-plans/)

Watch planning applications (תכניות בניין עיר) inside the **גינות העיר (Ginot HaIr)
community council** area of Jerusalem, from the Israel Planning Administration's
public ArcGIS service, and publish them as a sortable table (entry order) with
derived objection deadlines.

**Live page: https://reihlinstinct.github.io/ginot-hair-plans/**

Every workflow ends with a `Run summary` job that writes a summary to the top of the run page: which jobs ran, their result and duration, what was skipped and why, the commits and files the run changed, and which checks cover those changes (`.github/ci-coverage-map.json` declares the coverage; files matching no mapping are flagged). The script is `scripts/ci/run_summary.py`.

## Purpose

Built to help the Ginot HaIr community urban planner follow plans in the
council area: what is new, what is open for objections (and until when -
derived), what has been reviewed, and what needed no action. The planner's
own tracking states (new / reviewed / objection filed / no objection needed /
urgent) live in a local, never-published file (`data/plan_status.json`,
gitignored). Nothing is ever filed automatically - the repo only informs a
human reviewer.

## Pipeline

1. `src/ginot/dwg.py` - convert the municipal community-council DWG export
   (AutoCAD AC1024, EPSG:2039) to polygons via LibreDWG `dwg2dxf` + `ezdxf`
   (repairs the broken ESRI-WKT XRECORD LibreDWG emits).
2. `src/ginot/select.py` - the municipal layer ships 53 *unnamed* polygons;
   Ginot HaIr is identified geometrically (landmark-driven greedy union,
   verified against the municipal GIS outline, Oct 2026): polygons #37+#39+#46,
   ~6.10 km2. Committed derived result: `data/council_ginot_hair.geojson`.
3. `src/ginot/iplan.py` - spatial-intersect query against
   `https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/<service>/MapServer/1/query`
   (`xplan_without_77_78` for active plans; `Xplan_77_78` for the 77/78 track).
   Read-only, no account. The server needs legacy TLS - we shell out to curl.
4. `src/ginot/outputs.py` - plan table: number, name, status, deposit /
   publication / approval dates, area, inside-vs-partial flag, Mavat link
   (`pl_url`), and a **derived** objection deadline (publication of the deposit
   notice + 60 days; flagged as derived - always verify against Mavat).
5. `src/ginot/tracking.py` - merge the planner's local tracking states into
   the rows; advisory urgent flag when an undecided plan's derived objection
   deadline is within 30 days.
6. `src/ginot/diff.py` - snapshot diff: new / removed / status-changed plans.
7. `src/ginot/page.py` - static Hebrew RTL page (Ginot HaIr palette).
   The plans table comes first, ordered by a stated relevance rule (open
   objection windows by nearest derived deadline, then active statuses
   newest-first, approved last); the page embeds the top 20 rows and loads
   the full set client-side from `rows.html`, approved plans are hidden by
   default (count stated, one click to bring back), and client-side
   filters (status, inside/partial, date range, free text, objection-open)
   always operate over all rows. An "סקירת AI" column links plans that
   have an AI-generated talking-points review, rendered as styled site
   pages from the repo markdown. The permit-requests section first loads
   `permits-default.html`, then loads the full `permits.html` on demand
   when a control needs the complete list. Dates display as DD.MM.YYYY with ISO
   values kept in data attributes. Colored status chips with a legend.
   Statistics, urgent section and recent changes (card) below the table;
   About + data sources + datasets list on a separate generated page;
   plus Atom `feed.xml`, `data.json`, and shields badge endpoints under
   `badge/` (including per-status plan-count badges).
8. `refresh.py` - weekly one-shot orchestration of all of the above.

## Mirrors

The site is published twice: **GitHub Pages** (primary,
`reihlinstinct.github.io/ginot-hair-plans`) and a **Cloudflare Pages**
mirror (`ginot-hair-plans.pages.dev`). To stay inside the free build quota,
the mirror's production branch is `mirror`, not `main`: Cloudflare builds
only when the `mirror` branch advances. The weekly refresh no longer pushes
that branch, requests a Pages build, or merges its data PR. Ordinary `main`
pushes do not advance the Cloudflare mirror, so it may lag until a maintainer
verifies the reviewed main commit and performs a separate continuation.
See [reviewed publication](docs/operations/data-publication.md) for the procedure.
PR preview deployments are disabled in the Cloudflare project.

## Weekly refresh

The workflow uses GitHub Actions cron `7 4 * * 2` (Tuesdays at 04:07 UTC),
not an external assistant wake. The repository kill switch and shared pending
PR guard run before collection. A pending weekly data PR produces a green
skip notice; a guard error fails closed.

When clear to run, it re-queries iplan and the land feed, diffs against
`snapshots/latest.json`, regenerates `out/` + `docs/`, and stages a PR. It
stops there for independent review and green CI before a normal merge. PR
creation is not publication. GitHub Pages may deploy the reviewed merge;
mirror continuation is separate. Do not rerun a collector just to publish
already-reviewed data. See the
[publication procedure](docs/operations/data-publication.md).

## Run it yourself

    pip install -r requirements.txt
    python3 refresh.py          # writes out/, docs/, snapshots/latest.json
    python3 -m pytest -q        # current unit/integration suite; browser jobs are separate

See [CHANGELOG.md](CHANGELOG.md) for notable changes. Only re-deriving the boundary from a fresh DWG export needs LibreDWG's
`dwg2dxf` (build notes in the wiki of the git history; the committed GeoJSON
is enough for the weekly run).

## Data API

Two layers, both read-only, public, and free to use. Everything updates on
each site refresh (weekly Tuesday 04:07 UTC, plus approved manual runs).

### Static files (GitHub Pages)

Served from `https://reihlinstinct.github.io/ginot-hair-plans/` with
`Access-Control-Allow-Origin: *` and a 10-minute cache:

| File | Contents |
| --- | --- |
| `data.json` | Full dataset: `{generated, rows[], changes[], permits[]}` - field names as they arrive from iplan / the municipal permit search |
| `open.json` | Open plans only (still in the planning process; definition: `station_desc != "אישור"`). `{generated, definition, count, plans[]}`, each row with `in_objection_period` - evaluated as of `generated` (Israel time); to recompute "now" from scratch, derive it from `objection_deadline_derived_60d_from_publication` instead |
| `feed.xml` | Atom feed of new/changed plans |
| `badge/*.json` | shields.io endpoints (plan count, per-status counts, updated date) |

### Query layer (Cloudflare Worker)

`https://ginot-hair-api.reihlinstinct.workers.dev` - a stateless read-only
Worker over the static files. CORS open, GET only, 5-minute edge cache,
best-effort rate limit (120 requests/minute/IP, per isolate).

| Route | Parameters |
| --- | --- |
| `/plans` | `open=1` (open plans only), `status` (substring of station_desc), `q` (number/name), `before=YYYY-MM-DD` (objection deadline on/before), `limit` (default 100, max 500) |
| `/permits` | `street`, `status`, `type` (sugbakasha), `q`, `limit` |
| `/open` | the static `open.json` |
| `/status` | `{generated, plans, permits}` counts |

Examples (use `-G` + `--data-urlencode` so Hebrew values are URL-encoded):

    curl -s -G https://ginot-hair-api.reihlinstinct.workers.dev/plans \
      --data-urlencode "open=1" --data-urlencode "limit=5"
    curl -s -G https://ginot-hair-api.reihlinstinct.workers.dev/permits \
      --data-urlencode "street=עמק רפאים"
    curl -s -G https://ginot-hair-api.reihlinstinct.workers.dev/plans \
      --data-urlencode "status=הפקדה" --data-urlencode "before=2026-12-31"

Limitations: no server-side joins or aggregation (filtering is substring
matching on the fields above; anything richer happens client-side over
`data.json`); objection deadlines are derived estimates, not legal dates;
the permit dataset is a work-in-progress parcel scan, backfilled in four
280-parcel windows daily (03:00,09:00,15:00,21:00 UTC) with serial requests spaced3seconds apart until all 4,739 parcels are
covered (see the permits section caveat on the site); the rate limit is best-effort, not contractual.

### Permit scan recovery

While a scan runs, it commits `data/permit_requests.json` to the scratch
`scan-checkpoint` branch every 15 parcels, then every 15 detail records and at
completion. A restart with the same offset and limit resumes saved parcels and
skips details already present. Completed parcel checkpoints also resume details.
Checkpoint writes retry three times, then stop rather than continue unprotected.
The last successful remote checkpoint survives cancellation, timeout or runner
loss; unfinished work since that checkpoint must be fetched again. A blocked
Actions account delays the restart, but does not delete remote checkpoints or
published data. The old checkpoint format is preserved. Already-running jobs
keep their checked-out code; the hardening applies to subsequent runs (#251).

### גישה לנתונים (API) - תקציר

שתי שכבות, שתיהן לקריאה בלבד, ציבוריות ובחינם, עם CORS פתוח. הכל מתעדכן
בכל רענון של האתר (שבועי, יום שלישי 04:07 UTC, ורענונים ידניים).

- **קבצים סטטיים** תחת `https://reihlinstinct.github.io/ginot-hair-plans/`:
  `data.json` (כל הנתונים), `open.json` (תכניות פתוחות בלבד, עם
  `in_objection_period`), `feed.xml` (Atom), `badge/*.json` (תגי shields).
- **שכבת שאילתות** ב-`https://ginot-hair-api.reihlinstinct.workers.dev`:
  `/plans` (`open=1`, `status`, `q`, `before`, `limit`), `/permits`
  (`street`, `status`, `type`, `q`, `limit`), `/open`, `/status`.
  מטמון קצה 5 דקות; הגבלת קצב 120 בקשות לדקה (best-effort).
  דוגמה: `curl -s -G .../permits --data-urlencode "street=עמק רפאים"`.

## Data sources & attribution

- Plan data: **Israel Planning Administration (מנהל התכנון)** public iplan
  service (ags.iplan.gov.il), republished here as derived snapshots. Verify
  against the official source (Mavat links included per plan).
- Council boundary: derived from a Jerusalem municipal community-council GIS
  export (geometry only). The municipal DWG itself is **not** redistributed
  here.
- Base map in development overlays: © OpenStreetMap contributors.

## Security & engineering

Public repo. CI on every PR/push: pytest + ruff across Python 3.11-3.13
(pinned action SHAs, `contents: read`). Branch protection on `main`: PRs +
green CI required. Secret scanning + push protection, Dependabot alerts and
updates, CODEOWNERS, SECURITY.md. No credentials or personal data in the repo
- see SECURITY.md.

## Status & limitations

- `receiving_date` is used as "entry into the system" for the sort order;
  `open_date`/`date_saf` are also exported per plan.
- The objection deadline is a computed estimate (+60d); only plans in הפקדה
  status have a live objection window.
- Plan documents (הוראות/תשריט) from Mavat: feasibility research in progress
  (see issues); nothing is downloaded or auto-filed.

### Permit ordering

Permits are ordered by publication category (dated, published without a date,
then no publication evidence), newest date first, then permit number ascending
for ties. With JavaScript enabled, the 20-row cap applies after sorting
(#451, #676). Without JavaScript, only the generated fallback subset is shown;
the browser-side sort and filters do not run.

### Table search

Both tables' free-text search ignores only the following marks and spacing differences:
geresh/gershayim and ASCII or typographic quotes and primes (`׳ ״ ' " ’ “ ′`),
hyphens, maqaf and dashes, niqqud, invisible direction marks and repeated or
non-breaking spaces are ignored on both the query and the row (#413, #468).
Commas and other unlisted punctuation are retained.
The search normalization regression requires Node.js: it skips in Python-only
local environments, but missing Node.js is a test failure in CI (#671).
Plans are searched by number and official name, permits by their listed
fields. There are no hand-written aliases: a colloquial name that the source
data does not contain (for example a street name missing from a plan's
official name) does not match.

### Optional plan map

The collapsed map below the tables uses locally hosted Leaflet (BSD-2-Clause)
and OpenStreetMap standard tiles with visible attribution, browser Referer and
normal caching. No prefetch, offline download, paid account or key. It loads only
when opened. Points follow the table's filter/search, including all matching rows
beyond the first 20. Numbered markers and status text supplement the status colors;
the map legend is hidden until toggled. No-match filters show an empty state.

`plan-points.json` stores only representative point coordinates from the public
planning geometry, not entrances. A selected plan's boundary loads directly in
the visitor's browser from the public ArcGIS service on request, with no polygon
file stored in this repo or site. Source downtime does not disable the table.
This is an unofficial information aid, not a statutory map. See
[map design and source terms](design/plan-map.md) (#253).

## MCP server (read-only)

`python -m ginot.mcp_server` serves the public `docs/data.json` over stdio MCP
(tools: `search_plans`, `get_plan`, `upcoming_objection_windows`, `data_status`).
No network, no writes, no secrets, no planner-private files. Objection windows are
derived from publication dates, not official deadlines.

### Connecting it to an agent

stdio only (runs locally; there is no hosted endpoint). Clone the repo, then add to
Claude Desktop `claude_desktop_config.json` (or `.mcp.json` for Claude Code):

```json
{
  "mcpServers": {
    "ginot-hair-plans": {
      "command": "python3",
      "args": ["-m", "ginot.mcp_server", "--data", "docs/data.json"],
      "cwd": "/path/to/ginot-hair-plans",
      "env": {"PYTHONPATH": "src"}
    }
  }
}
```

Claude Code one-liner: `claude mcp add ginot-hair-plans -e PYTHONPATH=src -- python3 -m ginot.mcp_server --data docs/data.json`
(run it from the repo root). Restart the client; the four tools then appear.

### Filter links

On the homepage, "העתק קישור לסינון" copies both tables' current controls
into a public URL (`filters=1`). Hebrew searches, selected groups, checkboxes,
dates, plan sort and expanded rows round-trip. No filter params means the
usual defaults; unknown versions/values are ignored. Non-default permit links
wait for the full permit list, using the same load/filter path as manual input.
If clipboard access is unavailable or denied, a selectable link is shown.
Links expose the search text and filters to anyone with the URL. Copying is
explicit; the page does not automatically rewrite history or share anything.

Parameter names: `plan.` + `fq`, `fstatus`, `fflag`, `fobj`, `ffrom`, `fto`,
`fappr`, `expanded`, `sort`, `dir`; `permit.` + `pfq`, `pfstatus`, `pfsug`,
`pffrom`, `pfto`, `pfclosed`, `pfopenonly`, `pfscope`, `expanded`, `groups`.
Booleans use `0`/`1`, dates ISO YYYY-MM-DD, selected groups comma-separated;
defaults are omitted. Unknown params and anchors are preserved when copying.
No synonym/alias matching is added (#468 is separate).
