"""Prepare map overlays from public planning features, without fetching data.

Publication of provider geometry needs a separate terms check. This module
neither publishes files nor changes the scheduled refresh.
"""
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform


def plan_geometry(rings):
    """Convert ArcGIS rings in ITM to WGS84, preserving holes and islands.

    The even/odd fill rule handles independent shells, holes, and nested
    islands without depending on winding direction. Invalid rings are
    rejected rather than silently inventing a boundary.
    """
    geometry = None
    for ring in rings or []:
        polygon = Polygon(ring)
        if not polygon.is_valid or polygon.is_empty or polygon.area == 0:
            raise ValueError("invalid planning boundary ring")
        geometry = polygon if geometry is None else geometry.symmetric_difference(polygon)
    if geometry is None or geometry.is_empty:
        return None
    if not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("invalid planning boundary geometry")
    project = Transformer.from_crs(2039, 4326, always_xy=True).transform
    point = transform(project, geometry.representative_point())
    return {"geometry": mapping(transform(project, geometry)),
            "point": [point.x, point.y]}


def feature_collection(features):
    """Return an overlay with an explicit count of unavailable boundaries.

    Only an allowlist of public fields is carried; no raw provider attributes.
    The point is an interior representative location, not an address/entrance.
    """
    result = {"type": "FeatureCollection", "features": [], "missing_geometry": 0}
    for feature in features:
        attrs = feature.get("attributes", {})
        rings = (feature.get("geometry") or {}).get("rings")
        try:
            prepared = plan_geometry(rings)
        except (ValueError, TypeError):
            prepared = None
        if not prepared:
            result["missing_geometry"] += 1
            continue
        result["features"].append({
            "type": "Feature", "geometry": prepared["geometry"],
            "properties": {"pl_number": attrs.get("pl_number"),
                           "pl_name": attrs.get("pl_name"),
                           "station_desc": attrs.get("station_desc"),
                           "representative_point": prepared["point"]},
        })
    return result
