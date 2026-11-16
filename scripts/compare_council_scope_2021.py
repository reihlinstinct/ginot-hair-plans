"""Compare every permit row with the OLD council map, without changing source data.

Issue #529. The candidate is NOT a production boundary. Output retains all
input rows and appends a three-state candidate flag. Parcel-centroid inclusion
is a comparison method, not proof of a permit's exact address location.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

# Section: Non-mutating candidate comparison


def annotate(rows: list[dict], parcels: dict, candidate: dict) -> list[dict]:
    """Keep every row and field; missing/unusable parcel geometry stays unknown."""
    area = shape(candidate.get("geometry", candidate))
    if (
        not area.is_valid
        or area.is_empty
        or area.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise ValueError("invalid candidate boundary")
    by_key: dict[tuple[int, int], list] = {}
    for feature in parcels["features"]:
        props = feature["properties"]
        key = (int(props["gush"]), int(props["helka"]))
        geometry = shape(feature["geometry"])
        by_key.setdefault(key, []).append(geometry)
    output = []
    for row in rows:
        copied = dict(row)
        flag = None
        reason = "missing_parcel_geometry"
        try:
            key = (int(row["gush"]), int(row["helka"]))
        except (KeyError, ValueError, TypeError):
            key = None
        geometries = by_key.get(key, [])
        if geometries and all(g.is_valid and not g.is_empty for g in geometries):
            point = unary_union(geometries).centroid
            if area.boundary.covers(point):
                reason = "centroid_on_candidate_edge"
            else:
                flag = area.contains(point)
                reason = "parcel_centroid_inside" if flag else "parcel_centroid_outside"
        copied["in_scope_candidate_2021"] = flag
        copied["scope_candidate_2021_reason"] = reason
        output.append(copied)
    return output


# Section: Explicit output path, never overwrite a source


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--permits", type=Path, default=Path("data/permit_requests.json")
    )
    parser.add_argument(
        "--parcels", type=Path, default=Path("data/ginot_hair_parcels.geojson")
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("docs/design/council-map-2021-candidate.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.resolve() in {
        p.resolve() for p in (args.permits, args.parcels, args.candidate)
    }:
        parser.error("comparison output must not overwrite a source")
    data = json.loads(args.permits.read_text(encoding="utf-8"))
    rows = (
        data if isinstance(data, list) else data.get("rows", data.get("requests", []))
    )
    output = annotate(
        rows,
        json.loads(args.parcels.read_text(encoding="utf-8")),
        json.loads(args.candidate.read_text(encoding="utf-8")),
    )
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    counts = Counter(str(r["in_scope_candidate_2021"]) for r in output)
    print(json.dumps({"rows_preserved": len(output), "candidate_flags": dict(counts)}))


if __name__ == "__main__":
    main()
