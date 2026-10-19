"""DWG -> polygons (EPSG:2039).

The municipal export is a binary AutoCAD 2010 DWG. Conversion uses LibreDWG's
dwg2dxf (build from source: https://ftp.gnu.org/gnu/libredwg/), then ezdxf.

The source DWG embeds its CRS as an ESRI WKT XRECORD: Israel_TM_Grid
(EPSG:2039). LibreDWG writes that WKT with a raw newline inside the value,
which breaks strict DXF tag parsing - repair_dxf_wkt() rejoins it.
"""
import subprocess
from pathlib import Path

import ezdxf
from shapely.geometry import Polygon

CRS_WKT_MARKER = 'PROJCS["Israel_TM_Grid"'


def convert_dwg_to_dxf(dwg_path: str, dxf_path: str, dwg2dxf: str = "dwg2dxf") -> str:
    subprocess.run([dwg2dxf, "-o", str(dxf_path), str(dwg_path)], check=True)
    return str(dxf_path)


def repair_dxf_wkt(dxf_path: str, out_path: str) -> str:
    lines = Path(dxf_path).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if CRS_WKT_MARKER in line and not line.rstrip().endswith("]]"):
            lines[i] = line.rstrip("\r\n") + lines[i + 1]
            del lines[i + 1]
            break
    Path(out_path).write_text("".join(lines), encoding="utf-8")
    return out_path


def read_polygons(dxf_path: str) -> list[Polygon]:
    """All closed LWPOLYLINEs in modelspace as shapely Polygons (EPSG:2039 meters)."""
    doc = ezdxf.readfile(dxf_path)
    polys = []
    for e in doc.modelspace().query("LWPOLYLINE"):
        pts = [(p[0], p[1]) for p in e.get_points()]
        if e.closed and len(pts) >= 4:
            polys.append(Polygon(pts))
    return polys
