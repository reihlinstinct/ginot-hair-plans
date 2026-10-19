# ginot-hair-plans

Watch planning applications (תכניות בניין עיר) inside the **גינות העיר (Ginot HaIr)
community council** area of Jerusalem, from the Israel Planning Administration's
public ArcGIS service, and publish them as a sortable table (entry order) with
derived objection deadlines.

**Status: PRIVATE. Do not make public without the owner's explicit approval
(see Data & redistribution below).**

## What it does

1. `ginot.dwg` - convert the municipal community-council DWG export (AutoCAD
   AC1024, EPSG:2039) to polygons via LibreDWG `dwg2dxf` + `ezdxf`
   (includes repair of the broken ESRI-WKT XRECORD LibreDWG emits).
2. `ginot.select` - the municipal layer ships 53 *unnamed* council polygons.
   Ginot HaIr is identified geometrically: greedy union of the polygons
   covering a set of required neighborhood landmarks (Rehavia, Talbiya,
   Komemiyut, German+Greek Colony, Old Katamon, Givat Hordim, Gonenim, Nayot)
   while excluding forbidden ones (Baka, Shaare Hesed, Lev HaIr, Old City).
   Verified against the municipal GIS outline (Oct 2026). Result on the
   Oct-2026 export: polygons #37+#39+#46, ~6.10 km2.
   The derived union is committed as `data/council_ginot_hair.geojson`.
3. `ginot.iplan` - spatial query (intersects) against
   `https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/<service>/MapServer/1/query`
   (services: `xplan_without_77_78` for active plans, `Xplan_77_78` for the
   77/78 track - name is case-sensitive). Read-only, no account.
   NOTE: the server needs a legacy TLS handshake; we shell out to `curl`
   (python-requests/OpenSSL 3 is refused).
4. `ginot.outputs` - plan table: number, name, status, deposit/publication/
   approval dates, area, inside-vs-partial-overlap flag, Mavat link
   (`pl_url`), and a **derived** objection deadline (publication of deposit
   notice + 60 days - flagged as derived, verify against Mavat).
5. `ginot.diff` - snapshot diff: new plans, removed plans, status changes.
6. `ginot.page` - static Hebrew RTL page (`index.html`) sorted by entry date
   (`receiving_date` desc) with a "new this week" highlight, plus an Atom
   feed (`feed.xml`) of changes, plus `data.json`.
7. `refresh.py` - one-shot orchestration of all of the above, designed to be
   run weekly (Tuesdays) by any free scheduler.

## Data & redistribution

- **The municipal DWG itself is NOT committed.** Its redistribution terms were
  not verified; only the small derived council-boundary GeoJSON is committed.
  Do not commit municipal source data without checking the license.
- Plan data comes from the Planning Administration's public iplan API
  (government open data) and is re-published here as derived snapshots.
- The planner's tracking-state file (data/plan_status.json) is gitignored and
  lives only on the machine running the refresh - it is never published. A
  durable private store for it comes with the approved planner workflow.

## Install

    pip install -r requirements.txt
    # Only needed to re-derive the boundary from the DWG (not for refresh):
    # build LibreDWG from source for dwg2dxf:
    #   curl -LO https://ftp.gnu.org/gnu/libredwg/libredwg-0.13.3.tar.xz
    #   ./configure --disable-bindings --disable-write --disable-trace && make -j1 CFLAGS='-O1 -g0'
    #   (parallel -j4 builds may OOM on small machines)

## Usage

    # weekly refresh (uses the committed council GeoJSON - no DWG needed)
    python refresh.py
    # outputs (committed to the repo by the weekly run):
    #   out/ginot_hair_plans.{csv,xlsx}, out/changes.json,
    #   snapshots/latest.json, site/{index.html,feed.xml,data.json}

    # re-derive the council polygon from a fresh municipal DWG export
    python -m ginot.derive data/municipal_councils.dwg   # TODO via ginot.dwg + ginot.select

## Weekly refresh scheduling (no GitHub Actions - billing-blocked)

Pick one:
- **Agent-side scheduled run (current default)**: our Instinct agent runs
  `python refresh.py` on a weekly Tuesday wake and pushes the result
  (`out/`, `site/`, `snapshots/`) to this repo. Zero cost, no new accounts.
- Free external cron (e.g. cron-job.org free tier) hitting a small hook.
- Free CI minutes on another host (Codeberg / GitLab free tier).

## Notifications

- `site/feed.xml` - Atom feed of new/changed plans (free, no accounts;
  recommended public channel once the page is public).
- The page highlights rows that are new since the previous snapshot.
- The agent pings the owner with the weekly diff summary.

## Tests

    python3 -m pytest -q

Unit tests cover council selection + landmark verification, date conversion
and the derived objection-deadline fallback chain, inside/partial
classification, entry-order sorting, snapshot diffing, and page/feed rendering.
No network access in tests.

## Notes / known caveats

- `receiving_date` is used as "entry into the system" for the arrival-order
  sort; `open_date`/`date_saf` are also exported if the semantics need to move.
- Only plans in הפקדה status have a meaningful live objection deadline.
- GitHub Pages needs a public repo on the free tier - publishing the page
  waits for the owner's go-public approval.
