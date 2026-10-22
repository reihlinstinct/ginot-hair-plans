# Map functional checks

`python -m pytest -q tests/test_map_browser.py`

Eight Chromium tests build/serve the actual generated site and use DOM clicks,
input, keyboard activation and visible-element assertions. External public
geometry responses are deterministic mocks and OSM tile requests are blocked.
The dedicated CI browser job runs this module alongside the general site suite.

- Initial twenty table rows exactly match the boundary query; show-all fallback.
- Search, column sort, plan status chip, reset and empty results synchronize.
- Global boundary switch starts on; off leaves unnumbered accessible points.
- Per-plan loading with global mode off, including keyboard marker activation.
- Real map-coordinate clicks inside and outside polygons; smaller overlap first.
- Citywide overlay cannot intercept clicks; holes and MultiPolygon supported.
- Geometry-service failure leaves usable point and popup; quick filter cleanup.
- Permit closed status hidden by default/reset, explicitly selectable; permit
  chip does not change plan/map filters.

Tests assert browser errors remain empty. The full suite also verifies committed
HTML carries the permit filter script and only one plan-specific legend.
