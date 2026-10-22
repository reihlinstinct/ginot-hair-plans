# ginot-hair-plans

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
   pages from the repo markdown. A permit-requests section (DRAFT) loads
   the same way from `permits.html`. Dates display as DD.MM.YYYY with ISO
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
only when the weekly refresh workflow (or a manual run of it) pushes
`main` to `mirror` after merging its publish PR - ordinary pushes to
`main` do not trigger a mirror build. PR preview deployments are disabled
in the Cloudflare project (Settings > Builds > Branch control).

## Weekly refresh

Runs every **Tuesday morning** from an external scheduler (the owner's
assistant on a weekly wake - GitHub Actions scheduling is intentionally not
used for the recurring run). It re-queries iplan, diffs against
`snapshots/latest.json`, regenerates `out/` + `docs/`, and commits the result
to this repo. New/changed plans are surfaced on the page ("new this week"),
in `feed.xml`, and in a summary ping to the owner.

## Run it yourself

    pip install -r requirements.txt
    python3 refresh.py          # writes out/, docs/, snapshots/latest.json
    python3 -m pytest -q        # 12 tests, no network needed

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
| `open.json` | Open plans only (still in the planning process; definition: `station_desc != "אישור"`). `{generated, definition, count, plans[]}`, each row with `in_objection_period` |
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
the permit dataset is a work-in-progress parcel scan, backfilled in two
280-parcel windows daily (03:00 + 09:00 UTC) until all 4,739 parcels are
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

Public repo. CI on every PR/push: pytest + ruff across Python 3.10-3.13
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
