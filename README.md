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
