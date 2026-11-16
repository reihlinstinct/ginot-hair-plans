"""Optional map markup; real boundaries are fetched in the visitor browser only."""

from .i18n import t as _t
from .page_resources import _e

# Strings the static plan-map.js needs, exposed via i18n.js_snippet (the file
# keeps its Hebrew literals as fallback for old pages without the object).
MAP_JS_KEYS = [
    "mapjs.plan_prefix",
    "mapjs.status_unknown",
    "mapjs.load_boundary",
    "mapjs.mavat",
    "mapjs.ai_review",
    "mapjs.overlap",
    "mapjs.permits_same_parcel",
    "mapjs.permit_point_note",
    "mapjs.permits_title",
    "mapjs.permits_status",
    "mapjs.boundaries_off",
    "mapjs.too_many",
    "mapjs.zoom_in",
    "mapjs.no_match",
    "mapjs.status_rows",
    "mapjs.some_failed",
    "mapjs.loading_boundaries",
    "mapjs.boundary_unavailable",
    "mapjs.loading_map",
    "mapjs.map_unavailable",
    "mapjs.legend_line",
    "mapjs.legend_permits",
]


def panel(lang: str = "he", pre: str = "") -> str:
    """The map <details> panel in lang; pre is the relative prefix from the
    page back to the site root ("" for the default-language page)."""
    return f"""<details id="plan-map-panel" class="plan-map-panel">
<summary>{_e(_t(lang, "map.summary"))}</summary>
<p>{_e(_t(lang, "map.intro"))}</p>
<label class="map-boundary-control"><input id="map-boundaries" type="checkbox" checked> {_e(_t(lang, "map.boundaries_label"))}</label>
<button id="map-legend-toggle" type="button" aria-expanded="false" aria-controls="map-legend">{_e(_t(lang, "map.legend_toggle"))}</button>
<div id="map-legend" hidden></div>
<p id="map-status" role="status">{_e(_t(lang, "map.status_open"))}</p>
<div id="plan-map" aria-label="{_e(_t(lang, "map.aria"))}" tabindex="0"></div>
<p>{_e(_t(lang, "map.note"))}</p>
<p><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a> · {_e(_t(lang, "map.credit"))}</p>
</details>
<script src="{pre}plan-map.js" defer></script>"""


# Backwards-compatible default panel (Hebrew, site root).
PANEL = panel()
