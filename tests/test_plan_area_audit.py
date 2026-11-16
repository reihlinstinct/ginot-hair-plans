"""Full-area anomaly diagnostics preserve source values and handle partial plans."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "area_audit", ROOT / "scripts/audit_plan_area.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

# Section: Synthetic full-area geometry


def rectangle(width, height, x=0, y=0):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height], [x, y]]


def feature(number, raw, rings):
    return {
        "attributes": {"pl_number": number, "pl_area_dunam": raw},
        "geometry": {"rings": rings},
    }


# Section: Reported cases, immutable source and legitimate partial plans


@pytest.mark.parametrize(
    "number,raw,area_m2,expected",
    [
        ("101-1336049", 4105.0, 4104.918444, "suspected_square_metres_in_dunam_field"),
        ("101-0055293", 1.281, 1279.752490, "consistent_with_geometry"),
        (
            "101-0092098",
            125942098.69,
            130074766.069,
            "suspected_square_metres_in_dunam_field",
        ),
        (
            "synthetic-large-partial",
            130074.766,
            130074766.069,
            "consistent_with_geometry",
        ),
    ],
)
def test_regressions_use_full_geometry_and_never_rescale(
    number, raw, area_m2, expected
):
    source = feature(number, raw, [rectangle(area_m2, 1)])
    original = deepcopy(source)
    result = audit.diagnose(source)
    assert result["pl_number"] == number
    assert result["raw_pl_area_dunam"] == raw
    assert result["area_quality"] == expected
    assert source == original


def test_holes_and_islands_are_not_added_as_extra_area():
    assert (
        audit.full_area_m2(
            [rectangle(10, 10), rectangle(4, 4, 2, 2), rectangle(1, 1, 3, 3)]
        )
        == 85
    )


def test_overlapping_crossing_rings_are_not_silently_interpreted():
    assert audit.full_area_m2([rectangle(10, 10), rectangle(10, 10, 5, 5)]) is None


@pytest.mark.parametrize("raw", [None, True, 0, -1, "4105"])
def test_invalid_raw_value_is_retained_but_not_classified(raw):
    result = audit.diagnose(feature("synthetic", raw, [rectangle(100, 100)]))
    assert result["raw_pl_area_dunam"] == raw
    assert result["area_quality"] == "invalid_or_missing_raw_area"


def test_intersection_attribute_cannot_turn_a_legitimate_partial_plan_into_anomaly():
    source = feature("synthetic-partial", 100000, [rectangle(10000, 10000)])
    source["attributes"]["intersection_dunam"] = 100
    assert audit.diagnose(source)["area_quality"] == "consistent_with_geometry"


def test_missing_geometry_does_not_imply_consistency():
    result = audit.diagnose(feature("synthetic", 1.281, []))
    assert result["area_quality"] == "unverified_geometry"
    assert result["raw_to_full_geometry_ratio"] is None


def test_non_thousandfold_mismatch_requires_review():
    assert (
        audit.diagnose(feature("synthetic", 50, [rectangle(100, 100)]))["area_quality"]
        == "area_mismatch_review_required"
    )


# Section: CRS, completeness and no-overwrite boundaries


@pytest.mark.parametrize(
    "source",
    [
        {"spatialReference": {"wkid": 4326}, "features": []},
        {
            "spatialReference": {"wkid": 2039},
            "exceededTransferLimit": True,
            "features": [],
        },
        {"spatialReference": {"wkid": 2039}, "error": {"code": 400}, "features": []},
    ],
)
def test_cli_rejects_unsafe_measurement_inputs(tmp_path, source):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source))
    out = tmp_path / "out.json"
    with pytest.raises(SystemExit):
        audit.main(["--source", str(path), "--out", str(out)])
    assert not out.exists()


def test_cli_never_overwrites_input(tmp_path):
    path = tmp_path / "source.json"
    path.write_text("original")
    with pytest.raises(SystemExit):
        audit.main(["--source", str(path), "--out", str(path)])
    assert path.read_text() == "original"
