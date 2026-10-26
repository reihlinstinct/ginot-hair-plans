import warnings

import pytest
from shapely.geometry import Point, shape

from ginot.mapdata import feature_collection, plan_geometry


def square(x, y, width):
    return [[x, y], [x + width, y], [x + width, y + width], [x, y + width], [x, y]]


def test_itm_projection_and_representative_point():
    result = plan_geometry([square(220000, 630000, 100)])
    lng, lat = result["point"]
    assert 35 < lng < 36 and 31 < lat < 32
    assert shape(result["geometry"]).covers(Point(lng, lat))


def test_hole_and_multipart_survive_projection():
    result = plan_geometry(
        [
            square(220000, 630000, 1000),
            square(220200, 630200, 300),
            square(222000, 632000, 50),
        ]
    )
    geometry = shape(result["geometry"])
    assert geometry.geom_type == "MultiPolygon"
    assert sum(len(p.interiors) for p in geometry.geoms) == 1
    assert geometry.covers(Point(*result["point"]))


def test_missing_and_invalid_geometry_are_not_geocoded():
    assert plan_geometry([]) is None
    with pytest.raises(ValueError):
        plan_geometry([[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]])
    data = feature_collection([{"attributes": {"pl_number": "synthetic"}}])
    assert data["missing_geometry"] == 1
    assert data["features"] == []


def test_only_public_fields_are_copied():
    data = feature_collection(
        [
            {
                "attributes": {
                    "pl_number": "synthetic",
                    "owner_email": "private@example.invalid",
                },
                "geometry": {"rings": [square(220000, 630000, 100)]},
            }
        ]
    )
    assert "owner_email" not in data["features"][0]["properties"]
    assert len(data["features"]) == 1


def test_plan_geometry_raises_no_shapely_deprecation_warning():
    """Issue #330: shapely.ops.transform() is deprecated in shapely 2.2+.

    Scoped to shapely's own DeprecationWarning (matching pytest.ini's
    `filterwarnings = error::DeprecationWarning:shapely`): escalating every
    DeprecationWarning here, including ones from other libraries' older
    numpy usage on Python 3.10, fails for a reason unrelated to this issue.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        warnings.filterwarnings(
            "error", category=DeprecationWarning, module=r"shapely(\.|$)"
        )
        result = plan_geometry([square(220000, 630000, 100)])
    assert result is not None


def test_permit_parcel_points_handle_holes_multipart_and_missing():
    from shapely.geometry import MultiPolygon, Polygon, mapping

    from ginot.mapdata import permit_points

    geometry = MultiPolygon([
        Polygon(square(35.21, 31.76, .01), [square(35.212, 31.762, .002)]),
        Polygon(square(35.24, 31.76, .001)),
    ])
    parcels = {'features': [{'properties': {'gush': 30000, 'helka': 12},
                            'geometry': mapping(geometry)}]}
    permits = [{'tik_num': 'one', 'gush': '030000', 'helka': '12', 'private': 'omit'},
               {'tik_num': 'two', 'gush': 30000, 'helka': 12},
               {'tik_num': 'missing', 'gush': 30000, 'helka': 13}]
    data = permit_points(permits, parcels)
    assert data['missing_location'] == ['missing']
    assert len(data['points']) == 2
    assert data['points'][0]['representative_point'] == data['points'][1]['representative_point']
    assert geometry.covers(Point(*data['points'][0]['representative_point']))
    assert set(data['points'][0]) == {'tik_num', 'representative_point'}


def test_permit_parcel_points_reject_invalid_or_non_wgs84_geometry():
    from shapely.geometry import Polygon, mapping

    from ginot.mapdata import permit_points

    parcels = {'features': [
        {'properties': {'gush': 1, 'helka': 1}, 'geometry': mapping(Polygon(square(220000, 630000, 100)))},
        {'properties': {'gush': 2, 'helka': 2}, 'geometry': None},
    ]}
    data = permit_points([{'tik_num': 'one', 'gush': 1, 'helka': 1},
                          {'tik_num': 'two', 'gush': 2, 'helka': 2}], parcels)
    assert data['points'] == []
    assert data['missing_location'] == ['one', 'two']
