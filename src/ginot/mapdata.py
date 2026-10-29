"""Prepare map overlays from public planning features, without fetching data.

Publication of provider geometry needs a separate terms check. This module
neither publishes files nor changes the scheduled refresh.
"""

import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, mapping


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
        geometry = (
            polygon if geometry is None else geometry.symmetric_difference(polygon)
        )
    if geometry is None or geometry.is_empty:
        return None
    if not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("invalid planning boundary geometry")
    project = Transformer.from_crs(2039, 4326, always_xy=True).transform
    point = shapely.transform(
        geometry.representative_point(), project, interleaved=False
    )
    return {
        "geometry": mapping(shapely.transform(geometry, project, interleaved=False)),
        "point": [point.x, point.y],
    }


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
        result["features"].append(
            {
                "type": "Feature",
                "geometry": prepared["geometry"],
                "properties": {
                    "pl_number": attrs.get("pl_number"),
                    "pl_name": attrs.get("pl_name"),
                    "station_desc": attrs.get("station_desc"),
                    "representative_point": prepared["point"],
                },
            }
        )
    return result


def permit_points(permits, parcels):
    """Join public parcel IDs to interior WGS84 points, never guess an address.

    Multiple parts of the same cadastral parcel are unioned before choosing an
    interior point. Only identifiers and representative coordinates leave here.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    def identifier(value):
        text = str(value).strip()
        return str(int(text)) if text.isascii() and text.isdigit() else None

    geometries = {}
    for feature in parcels.get('features', []):
        props = feature.get('properties') or {}
        key = (identifier(props.get('gush')), identifier(props.get('helka')))
        if None in key:
            continue
        try:
            geometry = shape(feature.get('geometry'))
            if (geometry.is_empty or not geometry.is_valid
                    or geometry.geom_type not in ('Polygon', 'MultiPolygon')):
                continue
            west, south, east, north = geometry.bounds
            if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                continue
        except (TypeError, ValueError, AttributeError):
            continue
        geometries.setdefault(key, []).append(geometry)
    positions = {}
    for key, parts in geometries.items():
        point = unary_union(parts).representative_point()
        positions[key] = [point.x, point.y]
    points, missing = [], []
    for permit in permits:
        tik = permit.get('tik_num')
        if not tik:
            continue
        key = (identifier(permit.get('gush')), identifier(permit.get('helka')))
        if key not in positions:
            missing.append(tik)
        else:
            points.append({'tik_num': tik, 'representative_point': positions[key]})
    return {'points': points, 'missing_location': missing,
            'source': 'Public cadastral parcel join (gush/helka); interior point, not entrance'}


def write_permit_points(permits, parcels_path, output_path):
    """Write a public points projection; missing source clears old positions."""
    import json
    from pathlib import Path

    path = Path(parcels_path)
    parcels = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data = permit_points(permits, parcels)
    Path(output_path).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data
