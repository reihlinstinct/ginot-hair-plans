"""Offline, non-mutating diagnostics for raw iplan area values (#868).

Reads a saved ArcGIS query response in EPSG:2039. Full geometry only; council
intersection area is deliberately not an input. Ratios suggest anomalies,
not intended legal units or replacement values. No fetching or publishing.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from shapely.geometry import Polygon

# Section: Full-geometry measurement


def full_area_m2(rings: list | None) -> float | None:
    """Even/odd shells, holes and islands; reject invalid or crossing rings."""
    geometry = None
    prior = []
    try:
        for ring in rings or []:
            polygon = Polygon(ring)
            if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
                return None
            if any(polygon.overlaps(other) for other in prior):
                return None
            prior.append(polygon)
            geometry = (
                polygon if geometry is None else geometry.symmetric_difference(polygon)
            )
    except (TypeError, ValueError):
        return None
    if geometry is None or geometry.is_empty or not geometry.is_valid:
        return None
    area = geometry.area
    return area if math.isfinite(area) and area > 0 else None


# Section: Anomaly policy (never automatic scaling)


def diagnose(feature: dict) -> dict:
    attrs = feature.get("attributes") or {}
    raw = attrs.get("pl_area_dunam")
    result = {
        "pl_number": attrs.get("pl_number"),
        "raw_pl_area_dunam": raw,
        "full_geometry_dunam": None,
        "raw_to_full_geometry_ratio": None,
        "area_quality": "unverified_geometry",
    }
    measured = full_area_m2((feature.get("geometry") or {}).get("rings"))
    if measured is None:
        return result
    dunam = measured / 1000
    result["full_geometry_dunam"] = dunam
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(raw)
        or raw <= 0
    ):
        result["area_quality"] = "invalid_or_missing_raw_area"
        return result
    ratio = raw / dunam
    result["raw_to_full_geometry_ratio"] = ratio
    if 0.95 <= ratio <= 1.05:
        result["area_quality"] = "consistent_with_geometry"
    elif 900 <= ratio <= 1100:
        result["area_quality"] = "suspected_square_metres_in_dunam_field"
    else:
        result["area_quality"] = "area_mismatch_review_required"
    return result


# Section: Offline CLI with explicit CRS and source preservation


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.out.exists() or args.out.resolve() == args.source.resolve():
        parser.error("choose a new output path; source files are never overwritten")
    data = json.loads(args.source.read_text(encoding="utf-8"))
    if data.get("spatialReference", {}).get("wkid") != 2039:
        parser.error("full-geometry measurements require explicit EPSG:2039")
    if data.get("error") or data.get("exceededTransferLimit"):
        parser.error("source response is incomplete or reports an error")
    features = data.get("features")
    if not isinstance(features, list):
        parser.error("source response must contain features")
    output = [diagnose(feature) for feature in features]
    # Unsupported/non-finite raw values are not rewritten into plausible
    # numbers. Strict JSON refuses non-finite numbers; the source stays intact.
    payload = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    args.out.write_text(payload, encoding="utf-8")
    print(f"wrote {len(output)} diagnostic records; no source values changed")


if __name__ == "__main__":
    main()
