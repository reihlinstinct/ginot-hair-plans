"""Explicit municipal-address point evidence for unresolved publications (#857).

No geocoding, parcel fabrication, address guessing, or network calls. A point
can resolve only an unknown parcel join, and only after an exact address and
neighborhood match. Polygon edges and duplicate evidence remain unresolved.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import unary_union

# Section: Evidence validation


def load_points(path: Path) -> list[dict]:
    """Load only the curated public evidence registry; missing means no fallback."""
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise TypeError("official point evidence must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise TypeError("invalid official point evidence record")
        for key in ("tik_num", "street", "house_number", "neighborhood"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError("official point evidence requires an exact address")
        date.fromisoformat(record["verified_at"])
        if record.get("crs") != "EPSG:2039":
            raise ValueError("official point evidence must use EPSG:2039")
        for key in ("x", "y"):
            value = record.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("invalid official point coordinate")
            if not math.isfinite(value):
                raise ValueError("non-finite official point coordinate")
        url = urlsplit(record["source_url"])
        query = parse_qs(url.fragment.partition("?")[2])
        if (
            url.scheme != "https"
            or url.netloc != "ykpubdata.jerusalem.muni.il"
            or url.path != "/"
            or url.fragment.partition("?")[0] != "/Details"
            or query.get("TikNum") != [record["tik_num"]]
            or query.get("Page") != ["LocationInfo"]
            or query.get("SystemCode") != ["26400046"]
        ):
            raise ValueError(
                "official point source must be the matching municipal case"
            )
    return records


# Section: Conservative point fallback


def resolve_official_points(
    rows: list[dict], records: list[dict], council_path: Path, neighborhoods: set
) -> None:
    """Resolve unknown joins only; never overrule a known parcel result.

    A row resolved here is marked ``in_polygon_source =
    "publication_point_evidence"`` so downstream consumers (baseline, alert
    payload, watch log) can tell a municipal point match from a parcel join.
    """
    if not records:
        return
    geojson = json.loads(council_path.read_text(encoding="utf-8"))
    if geojson.get("type") == "FeatureCollection":
        geometry = unary_union([shape(f["geometry"]) for f in geojson["features"]])
    else:
        geometry = shape(geojson.get("geometry", geojson))
    discarded = None
    if not geometry.is_valid:
        # The committed DWG export has zero-area ring spikes (#857). Accept
        # only a make_valid result consisting of ONE polygon plus linework,
        # with no polygon area change. Never silently fix crossings/overlaps.
        repaired = make_valid(geometry)
        parts = (
            list(repaired.geoms) if repaired.geom_type == "GeometryCollection" else []
        )
        polygons = [p for p in parts if p.geom_type in {"Polygon", "MultiPolygon"}]
        lines = [p for p in parts if p.geom_type in {"LineString", "MultiLineString"}]
        if (
            len(polygons) != 1
            or len(polygons) + len(lines) != len(parts)
            or not math.isclose(
                polygons[0].area, geometry.area, rel_tol=1e-12, abs_tol=1e-15
            )
        ):
            raise ValueError("council polygon needs a reviewed boundary repair")
        geometry = polygons[0]
        discarded = unary_union(lines)
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("invalid council polygon for official point evidence")
    transform = Transformer.from_crs(2039, 4326, always_xy=True)
    for row in rows:
        if row.get("in_polygon") is not None:
            continue
        matches = [r for r in records if r["tik_num"] == row.get("tik_num")]
        if len(matches) != 1:
            continue
        evidence = matches[0]
        address_keys = ("street", "house_number", "neighborhood")
        if any(row.get(k) != evidence[k] for k in address_keys):
            continue
        if row.get("neighborhood") not in neighborhoods:
            continue
        lon, lat = transform.transform(evidence["x"], evidence["y"])
        if not (math.isfinite(lon) and math.isfinite(lat)):
            continue
        point = Point(lon, lat)
        if geometry.boundary.covers(point) or (
            discarded is not None and discarded.covers(point)
        ):
            continue
        row["in_polygon"] = geometry.contains(point)
        row["in_polygon_source"] = "publication_point_evidence"
