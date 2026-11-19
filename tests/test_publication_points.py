"""Conservative official-point fallback for missing parcel joins (#857)."""

import importlib.util
import json
from pathlib import Path

import pytest
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "publication_points_test", ROOT / "scripts/vpn/publication_points.py"
)
points = importlib.util.module_from_spec(spec)
spec.loader.exec_module(points)

# Section: Synthetic evidence and geometry


def evidence(**changes):
    record = {
        "tik_num": "fixture",
        "street": "Synthetic street",
        "house_number": "1",
        "neighborhood": "Synthetic neighborhood",
        "crs": "EPSG:2039",
        "x": 220378,
        "y": 631339,
        "verified_at": "2026-11-16",
        "source_url": (
            "https://ykpubdata.jerusalem.muni.il/#/Details?TikNum=fixture"
            "&SystemCode=26400046&Page=LocationInfo"
        ),
    }
    return record | changes


def publication(**changes):
    return {
        "tik_num": "fixture",
        "street": "Synthetic street",
        "house_number": "1",
        "neighborhood": "Synthetic neighborhood",
        "in_polygon": None,
        "objection_deadline": None,
    } | changes


def polygon(tmp_path, *, outside=False):
    lon, lat = Transformer.from_crs(2039, 4326, always_xy=True).transform(
        220378, 631339
    )
    if outside:
        lon += 0.1
    ring = [
        [lon - 0.001, lat - 0.001],
        [lon + 0.001, lat - 0.001],
        [lon + 0.001, lat + 0.001],
        [lon - 0.001, lat + 0.001],
        [lon - 0.001, lat - 0.001],
    ]
    path = tmp_path / "council.json"
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}))
    return path


def resolve(rows, records, path):
    points.resolve_official_points(rows, records, path, {"Synthetic neighborhood"})


# Section: Point scope, address ambiguity and precedence


@pytest.mark.parametrize("outside,expected", [(False, True), (True, False)])
def test_unknown_parcel_join_uses_official_point(tmp_path, outside, expected):
    rows = [publication()]
    resolve(rows, [evidence()], polygon(tmp_path, outside=outside))
    assert rows[0]["in_polygon"] is expected
    assert rows[0]["objection_deadline"] is None
    assert "gush" not in rows[0] and "helka" not in rows[0]


@pytest.mark.parametrize(
    "changes",
    [{"street": None}, {"house_number": "1-3"}, {"neighborhood": "Other"}],
)
def test_ambiguous_or_mismatched_address_stays_unknown(tmp_path, changes):
    rows = [publication(**changes)]
    resolve(rows, [evidence()], polygon(tmp_path))
    assert rows[0]["in_polygon"] is None


def test_out_of_scope_neighborhood_is_not_broadened(tmp_path):
    rows = [publication(neighborhood="Other")]
    resolve(rows, [evidence(neighborhood="Other")], polygon(tmp_path))
    assert rows[0]["in_polygon"] is None


def test_duplicate_evidence_stays_unknown(tmp_path):
    rows = [publication()]
    resolve(rows, [evidence(), evidence()], polygon(tmp_path))
    assert rows[0]["in_polygon"] is None


@pytest.mark.parametrize("known", [False, True])
def test_known_parcel_result_is_never_overridden(tmp_path, known):
    rows = [publication(in_polygon=known)]
    resolve(rows, [evidence()], polygon(tmp_path, outside=known))
    assert rows[0]["in_polygon"] is known


def test_edge_point_stays_unknown(tmp_path):
    path = polygon(tmp_path)
    data = json.loads(path.read_text())
    lon, lat = Transformer.from_crs(2039, 4326, always_xy=True).transform(
        220378, 631339
    )
    data["coordinates"][0][0] = [lon, lat]
    data["coordinates"][0][-1] = [lon, lat]
    path.write_text(json.dumps(data))
    rows = [publication()]
    resolve(rows, [evidence()], path)
    assert rows[0]["in_polygon"] is None


# Section: Downstream provenance marker


def test_fallback_row_is_marked_with_its_source(tmp_path):
    rows = [publication()]
    resolve(rows, [evidence()], polygon(tmp_path))
    assert rows[0]["in_polygon_source"] == "publication_point_evidence"


@pytest.mark.parametrize("known", [None, False, True])
def test_untouched_rows_carry_no_source_marker(tmp_path, known):
    rows = [publication(in_polygon=known)]
    resolve(rows, [], polygon(tmp_path))
    assert "in_polygon_source" not in rows[0]


def test_feature_collection_council_input(tmp_path):
    bare = json.loads(polygon(tmp_path).read_text())
    path = tmp_path / "council_fc.json"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": bare}],
            }
        )
    )
    rows = [publication()]
    resolve(rows, [evidence()], path)
    assert rows[0]["in_polygon"] is True


def test_non_string_house_number_stays_unknown(tmp_path):
    rows = [publication(house_number=1)]
    resolve(rows, [evidence()], polygon(tmp_path))
    assert rows[0]["in_polygon"] is None
    assert "in_polygon_source" not in rows[0]


# Section: Jerusalem envelope


def test_committed_registry_points_are_inside_the_jerusalem_envelope():
    records = points.load_points(ROOT / "data/publication_point_evidence.json")
    assert records, "registry must not be empty for the envelope check"
    transform = Transformer.from_crs(2039, 4326, always_xy=True)
    for record in records:
        lon, lat = transform.transform(record["x"], record["y"])
        assert 31.65 <= lat <= 31.95, record
        assert 35.05 <= lon <= 35.35, record


@pytest.mark.parametrize(
    "changes",
    [
        {"x": 178000, "y": 658000},  # Tel Aviv area: north and west of the city
        {"x": 220378, "y": 700000},  # far north of Jerusalem
        {"x": 220378, "y": 600000},  # far south of Jerusalem
    ],
)
def test_out_of_envelope_registry_is_rejected(tmp_path, changes):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps([evidence(**changes)]))
    with pytest.raises(ValueError, match="Jerusalem envelope"):
        points.load_points(path)


# Section: Registry provenance and fail-closed loading


def test_missing_registry_keeps_old_behavior(tmp_path):
    assert points.load_points(tmp_path / "absent.json") == []


@pytest.mark.parametrize(
    "changes",
    [
        {"source_url": "https://example.com/"},
        {"tik_num": "other"},
        {"x": float("nan")},
        {"x": True},
        {"crs": "EPSG:4326"},
        {"verified_at": "not-a-date"},
        {"street": ""},
    ],
)
def test_bad_registry_fails_before_scope_resolution(tmp_path, changes):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps([evidence(**changes)]))
    with pytest.raises((ValueError, TypeError)):
        points.load_points(path)


def test_committed_evidence_resolves_only_matching_publication():
    records = points.load_points(ROOT / "data/publication_point_evidence.json")
    record = next(r for r in records if r["tik_num"] == "1983/0461.03")
    row = publication(
        **{k: record[k] for k in ("tik_num", "street", "house_number", "neighborhood")}
    )
    points.resolve_official_points(
        [row], records, ROOT / "data/council_ginot_hair.geojson", {"רחביה"}
    )
    assert row["in_polygon"] is True
    assert row["objection_deadline"] is None


# Section: Invalid polygon boundaries


def test_area_changing_self_intersection_is_not_repaired(tmp_path):
    path = tmp_path / "crossed.json"
    path.write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[35, 31], [36, 32], [35, 32], [36, 31], [35, 31]]],
            }
        )
    )
    with pytest.raises(ValueError, match="reviewed boundary repair"):
        resolve([publication()], [evidence()], path)


def test_zero_area_spike_can_be_removed_without_changing_scope(tmp_path):
    path = polygon(tmp_path)
    data = json.loads(path.read_text())
    ring = data["coordinates"][0]
    corner = ring[0]
    ring[1:1] = [[corner[0] - 0.001, corner[1] - 0.001], corner]
    path.write_text(json.dumps(data))
    rows = [publication()]
    resolve(rows, [evidence()], path)
    assert rows[0]["in_polygon"] is True


def test_point_on_discarded_linework_stays_unknown(tmp_path):
    path = polygon(tmp_path)
    data = json.loads(path.read_text())
    ring = data["coordinates"][0]
    lon, lat = Transformer.from_crs(2039, 4326, always_xy=True).transform(
        220378, 631339
    )
    corner = ring[0]
    # Zero-area spike from a corner to the evidence point: repair discards it
    # as linework, and a point on discarded linework must stay unknown.
    ring[1:1] = [[lon, lat], corner]
    path.write_text(json.dumps(data))
    rows = [publication()]
    resolve(rows, [evidence()], path)
    assert rows[0]["in_polygon"] is None
    assert "in_polygon_source" not in rows[0]


# Section: Fail-closed loading with clear errors and deferred council reads


@pytest.mark.parametrize("missing", ["verified_at", "source_url"])
def test_missing_provenance_fields_fail_with_clear_error(tmp_path, missing):
    record = evidence()
    del record[missing]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([record]))
    with pytest.raises(ValueError, match="verified_at and source_url"):
        points.load_points(path)


def test_council_is_not_loaded_when_no_row_matches(tmp_path):
    broken = tmp_path / "broken_council.json"
    broken.write_text("{ not json")
    rows = [publication(in_polygon=True), publication(tik_num="other")]
    resolve(rows, [evidence()], broken)
    assert rows[0]["in_polygon"] is True
    assert rows[1]["in_polygon"] is None
