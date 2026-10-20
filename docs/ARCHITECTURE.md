# Architecture

```
municipal DWG (EPSG:2039, user export, not committed)
   |  dwg2dxf (LibreDWG) + ezdxf          [src/ginot/dwg.py]
   v
53 unnamed council polygons
   |  landmark-driven union selection      [src/ginot/select.py]
   v
Ginot HaIr polygon -> data/council_ginot_hair.geojson (committed, WGS84)
   |  ArcGIS spatial intersect (curl)      [src/ginot/iplan.py]
   v
plan features (iplan public API, EPSG:2039)
   |  dates, inside/partial, derived objection deadline [src/ginot/outputs.py]
   |  + planner tracking states            [src/ginot/tracking.py, local only]
   v
out/*.csv|xlsx, snapshots/latest.json, out/changes.json
   |  snapshot diff                        [src/ginot/diff.py]
   v
static site: index.html (entry order), feed.xml, data.json [src/ginot/page.py]
   ^
   |  weekly Tuesday orchestration         [refresh.py + external scheduler]
```

Data flows one way: public iplan data in, derived artifacts out. The only
non-public artifact is the planner's local `data/plan_status.json`.

## Diagrams

Rule: anything that needs design gets a Mermaid diagram (in the issue or in
the docs). Generic example data only; no real plates, locations or
personal data.

### System context

```mermaid
flowchart LR
  IP[iplan public API] --> PIPE
  MIR[permit mirror<br/>over.org.il] --> PIPE
  MUN[municipality site<br/>via VPN runner] --> PIPE
  subgraph GH[GitHub, public repo]
    PIPE[scheduled workflows<br/>weekly refresh, permit feed]
    DATA[data/*.json committed by bot PRs]
    SITE[GitHub Pages site<br/>index, feed.xml, data.json, badges]
    CI[CI: ruff, pytest, browser tests, CodeQL]
  end
  PIPE --> DATA --> SITE
  CI --> DATA
  USER[planner / owner] --> SITE
  USER -. local only .-> LOCAL[data/plan_status.json<br/>gitignored tracking state]
```

### Data flow

```mermaid
flowchart TB
  DWG[municipal DWG<br/>local export, not committed] --> SEL[select.py<br/>council polygon]
  SEL --> GEO[council_ginot_hair.geojson]
  GEO --> IPL[iplan.py<br/>spatial query]
  IPL --> OUT[outputs.py<br/>dates, deadline, inside/partial]
  TRK[tracking.py<br/>local states] --> OUT
  OUT --> SNAP[snapshots/latest.json, out/*.csv]
  SNAP --> DIFF[diff.py] --> PAGE[page.py]
  PAGE --> PUB[docs/index.html, feed.xml, data.json]
  ENR[permit_enrich<br/>publication dates] --> OUT
```

### Change pipeline

```mermaid
flowchart LR
  I[issue] --> B[branch + PR]
  B --> CK[ruff, pytest, site-browser, CodeQL]
  CK --> UP{green and up to date?}
  UP -- yes --> M[squash merge]
  UP -- no --> B
  M --> P[Pages republished]
```
