"""The 2021 map comparison preserves every row and never changes production."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "scope_comparison", ROOT / "scripts/compare_council_scope_2021.py"
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)

# Section: Synthetic comparison fixtures


def rectangle(x, y, width=1):
    return {
        "type": "Polygon",
        "coordinates": [
            [[x, y], [x + width, y], [x + width, y + width], [x, y + width], [x, y]]
        ],
    }


def parcels():
    return {
        "features": [
            {"properties": {"gush": 1, "helka": 1}, "geometry": rectangle(0, 0)},
            {"properties": {"gush": 1, "helka": 2}, "geometry": rectangle(5, 5)},
        ]
    }


# Section: All-row preservation and three-state classification


def test_preserves_all_rows_original_fields_and_input_objects():
    rows = [
        {"tik_num": "inside", "gush": 1, "helka": 1, "address": "keep"},
        {"tik_num": "outside", "gush": 1, "helka": 2},
        {"tik_num": "unknown", "gush": 99, "helka": 99},
        {"tik_num": "no-key"},
    ]
    original = deepcopy(rows)
    output = comparison.annotate(rows, parcels(), rectangle(-1, -1, 3))
    assert rows == original
    assert len(output) == len(rows)
    assert [r["in_scope_candidate_2021"] for r in output] == [True, False, None, None]
    for before, after in zip(rows, output, strict=True):
        assert all(after[k] == v for k, v in before.items())


def test_edge_centroid_is_unknown():
    output = comparison.annotate(
        [{"gush": 1, "helka": 1}], parcels(), rectangle(0.5, 0.5, 3)
    )
    assert output[0]["in_scope_candidate_2021"] is None
    assert output[0]["scope_candidate_2021_reason"] == "centroid_on_candidate_edge"


def test_invalid_boundary_is_not_silently_repaired():
    with pytest.raises(ValueError, match="invalid candidate boundary"):
        comparison.annotate([], parcels(), rectangle(0, 0, 0))


def test_cli_refuses_to_overwrite_any_input(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("original")
    with pytest.raises(SystemExit):
        comparison.main(["--permits", str(source), "--out", str(source)])
    assert source.read_text() == "original"


# Section: Checked candidate provenance


def test_candidate_is_explicitly_old_official_map_and_valid_geometry():
    candidate = json.loads(
        (ROOT / "reference/scope/council_map_2021_candidate.geojson").read_text()
    )
    assert candidate["properties"]["pdf_creation_date"] == "2021-10-13"
    assert "NOT production" in candidate["properties"]["name"]
    assert candidate["properties"]["source_area_m2"] == pytest.approx(3147067, abs=1)
    assert comparison.shape(candidate["geometry"]).is_valid


# Section: Source extraction controls


def extractor():
    spec = importlib.util.spec_from_file_location(
        "scope_extractor", ROOT / "scripts/extract_council_scope_2021.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grid_fit_reproduces_printed_ticks():
    slope, offset, residual = extractor().fit_ticks(
        [(0, 100), (2, 104), (4, 108), (6, 112)]
    )
    assert slope == 2
    assert offset == 100
    assert residual == 0


def test_grid_fit_rejects_missing_or_inconsistent_ticks():
    with pytest.raises(ValueError):
        extractor().fit_ticks([(0, 100)])
    with pytest.raises(ValueError):
        extractor().fit_ticks([(0, 100), (2, 104), (4, 108), (6, 150)])


def test_extraction_refuses_changed_source_before_pdf_processing(tmp_path):
    pdf = tmp_path / "wrong.pdf"
    pdf.write_bytes(b"synthetic, not the official map")
    with pytest.raises(SystemExit):
        extractor().main(["--pdf", str(pdf), "--out", str(tmp_path / "out.json")])
    assert not (tmp_path / "out.json").exists()
