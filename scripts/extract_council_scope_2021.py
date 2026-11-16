"""Reproduce #529's comparison boundary from the exact OLD council service PDF.

Requires PyMuPDF as an optional local research dependency, not a production
package. No network. Checks the source hash before extracting vector paths.
Writes only a new comparison GeoJSON, never the production council polygon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform, unary_union

# Section: Printed-grid fit


def fit_ticks(ticks: list[tuple[float, int]]) -> tuple[float, float, float]:
    """Least-squares affine map from PDF coordinates to printed ITM ticks."""
    if len(ticks) < 4:
        raise ValueError("not enough printed grid ticks")
    xmean = sum(x for x, _ in ticks) / len(ticks)
    ymean = sum(y for _, y in ticks) / len(ticks)
    slope = sum((x - xmean) * (y - ymean) for x, y in ticks) / sum(
        (x - xmean) ** 2 for x, _ in ticks
    )
    offset = ymean - slope * xmean
    residual = max(abs(slope * x + offset - y) for x, y in ticks)
    if residual > 0.01:
        raise ValueError("printed grid fit differs from the checked source")
    return slope, offset, residual


# Section: Exact-source vector extraction


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("reference/scope/council_map_2021_candidate.geojson"),
    )
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("choose a new output path; source files are never overwritten")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))["properties"]
    digest = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if digest != metadata["source_sha256"]:
        parser.error("PDF hash differs from reviewed source")
    import pymupdf

    with pymupdf.open(args.pdf) as document:
        page = document[0]
        xticks, yticks = [], []
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            if not word.isdigit() or len(word) != 6:
                continue
            if word.startswith(("21", "22")) and y0 < 80:
                xticks.append(((x0 + x1) / 2, int(word)))
            if word.startswith(("62", "63")) and x0 > 3300:
                yticks.append(((y0 + y1) / 2, int(word)))
        ax, bx, rx = fit_ticks(xticks)
        ay, by, ry = fit_ticks(yticks)
        polygons = []
        for drawing in page.get_drawings():
            if drawing.get("color") != (0.0, 0.43922001123428345, 1.0):
                continue
            if len(drawing["items"]) < 100:  # Exclude the legend symbol.
                continue
            coordinates = []
            for kind, *points in drawing["items"]:
                if kind != "l":
                    raise ValueError("unexpected curve in checked boundary")
                if not coordinates:
                    coordinates.append((ax * points[0].x + bx, ay * points[0].y + by))
                coordinates.append((ax * points[-1].x + bx, ay * points[-1].y + by))
            if coordinates[0] != coordinates[-1]:
                raise ValueError("source boundary is not closed")
            polygon = Polygon(coordinates)
            if not polygon.is_valid:
                raise ValueError("source boundary is not valid")
            polygons.append(polygon)
        if len(polygons) != 5:
            raise ValueError("expected five checked blue boundary paths")
    geometry = unary_union(polygons)
    projection = Transformer.from_crs(2039, 4326, always_xy=True).transform
    output = {
        "type": "Feature",
        "properties": metadata,
        "geometry": mapping(transform(projection, geometry)),
    }
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"area_m2": geometry.area, "grid_fit_residual_m": max(rx, ry)}))


if __name__ == "__main__":
    main()
