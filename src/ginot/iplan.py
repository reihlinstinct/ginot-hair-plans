"""Spatial query against the Planning Administration public ArcGIS service.

Endpoint (read-only, no account):
  https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/<service>/MapServer/1/query
Services: xplan_without_77_78 (active plans), Xplan_77_78 (77/78 procedures -
case-sensitive). Layers are EPSG:2039 polygons.

Note: the server requires a legacy TLS handshake that python-requests/OpenSSL
3 refuses; curl negotiates it fine, so we shell out to curl.
"""
import json
import subprocess

from shapely.geometry import Polygon

BASE = "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic"
FIELDS = ("pl_number,pl_name,station_desc,internet_short_status,"
          "entity_subtype_desc,depositing_date,pl_last_deposit_date,"
          "pl_date_advertise,receiving_date,open_date,date_saf,pl_date_8,"
          "pl_area_dunam,pl_url,mp_id,entity_subtype_desc,"
          "jurstiction_area_name,last_update_date")


def _rings(poly: Polygon, simplify_m: float = 5.0) -> list:
    p = poly.simplify(simplify_m, preserve_topology=True)
    return [[[round(x, 2), round(y, 2)] for x, y in p.exterior.coords]]


def query_plans(council: Polygon, service: str = "xplan_without_77_78",
                layer: int = 1, out_fields: str = FIELDS,
                return_geometry: bool = True, timeout: int = 90) -> list[dict]:
    geom = json.dumps({"rings": _rings(council), "spatialReference": {"wkid": 2039}})
    url = f"{BASE}/{service}/MapServer/{layer}/query"
    cmd = ["curl", "-s", "-m", str(timeout), url,
           "--data-urlencode", "f=json",
           "--data-urlencode", "geometry=" + geom,
           "--data-urlencode", "geometryType=esriGeometryPolygon",
           "--data-urlencode", "inSR=2039",
           "--data-urlencode", "spatialRel=esriSpatialRelIntersects",
           "--data-urlencode", "outFields=" + out_fields,
           "--data-urlencode", f"returnGeometry={'true' if return_geometry else 'false'}",
           "--data-urlencode", "outSR=2039",
           "--data-urlencode", "resultRecordCount=2000"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    return data.get("features", [])
