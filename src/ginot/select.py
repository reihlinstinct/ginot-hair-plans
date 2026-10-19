"""Identify the Ginot HaIr council area among the unnamed municipal polygons.

The municipal layer ships 53 closed polygons with no name attributes. The
council is identified geometrically: the union of polygons must contain every
REQUIRED landmark and exclude every FORBIDDEN one (verified against the
municipal GIS screenshot of the גינות העיר outline, Oct 2026).

Result with the Oct-2026 export: polygons #37 + #39 + #46
(Rehavia/Talbiya/Komemiyut/German+Greek Colony + Old Katamon + Gonenim/Givat
Hordim), ~6.10 km2. Baka, Shaare Hesed and Lev HaIr stay outside.
"""
from pyproj import Transformer
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

_TO_2039 = Transformer.from_crs("EPSG:4326", "EPSG:2039", always_xy=True)

REQUIRED_LANDMARKS = {
    "Rehavia": (35.2165, 31.7745),
    "Talbiya": (35.2195, 31.7700),
    "Komemiyut": (35.2142, 31.7698),
    "GermanColony": (35.2182, 31.7647),
    "GreekColony": (35.2123, 31.7615),
    "KatamonOld": (35.2076, 31.7510),
    "GivatHordim": (35.2035, 31.7535),
    "Gonenim": (35.2100, 31.7570),
    "Nayot": (35.2015, 31.7695),
}
FORBIDDEN_LANDMARKS = {
    "Baka": (35.2210, 31.7590),
    "ShaareHesed": (35.2125, 31.7820),
    "LevHaIr": (35.2200, 31.7805),
    "OldCity": (35.2340, 31.7767),
}


def _pt(lonlat):
    return Point(*_TO_2039.transform(*lonlat))


def select_council(polys: list[Polygon]) -> tuple[Polygon, list[int]]:
    """Greedy union: seed with the polygon covering most required landmarks,
    then add touching polygons that cover still-uncovered required landmarks
    without covering any forbidden one."""
    req = {k: _pt(v) for k, v in REQUIRED_LANDMARKS.items()}
    frb = {k: _pt(v) for k, v in FORBIDDEN_LANDMARKS.items()}

    def covers(i, pts):
        return {k for k, p in pts.items() if polys[i].contains(p)}

    clean = [i for i in range(len(polys)) if not covers(i, frb)]
    seed = max(clean, key=lambda i: len(covers(i, req)))
    chosen = [seed]
    covered = covers(seed, req)
    remaining = set(req) - covered
    while remaining:
        best, best_gain = None, 0
        for i in clean:
            if i in chosen or not polys[i].intersects(unary_union([polys[j] for j in chosen])):
                continue
            gain = len(covers(i, req) & remaining)
            if gain > best_gain:
                best, best_gain = i, gain
        if best is None:
            raise ValueError(f"cannot cover landmarks: {sorted(remaining)}")
        chosen.append(best)
        covered |= covers(best, req)
        remaining = set(req) - covered
    union = unary_union([polys[i] for i in chosen])
    if union.geom_type != "Polygon":
        union = max(union.geoms, key=lambda g: g.area)
    return union, sorted(chosen)


def verify(union: Polygon) -> dict:
    inside = [k for k, v in REQUIRED_LANDMARKS.items() if union.contains(_pt(v))]
    outside = [k for k, v in FORBIDDEN_LANDMARKS.items() if not union.contains(_pt(v))]
    ok = len(inside) == len(REQUIRED_LANDMARKS) and len(outside) == len(FORBIDDEN_LANDMARKS)
    return {"ok": ok, "required_inside": inside, "forbidden_outside": outside,
            "area_km2": round(union.area / 1e6, 3)}
