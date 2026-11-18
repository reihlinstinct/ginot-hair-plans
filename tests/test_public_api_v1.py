"""Versioned read-only JSON contract: api/v1/* (#121).

The build writes api/v1/plans.json, permits.json, changes.json and
meta.json next to data.json (a deprecated alias for one release), with
public fields only - underscore-internal fields never cross into v1.
Changes within v1 are additive only, so the schemas require a stable
core and allow additional properties.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ginot import public_api

SCHEMA_DIR = ROOT / "src" / "ginot" / "static" / "api" / "v1" / "schema"


def _write(tmp_path):
    rows = [
        {
            "pl_number": "101-1",
            "pl_name": "תכנית",
            "station_desc": "אישור",
            "_rank": 3,
            "secret_field": "dropped",
        }
    ]
    changes = [{"kind": "status_change", "pl_number": "101-1", "extra": 1}]
    permits = [{"tik_num": "T/1", "gush": 1, "_map_missing": False}]
    public_api.write_v1(str(tmp_path), rows, changes, permits, "2026-11-18")
    return tmp_path / "api" / "v1"


# Section: contract shape


def test_write_v1_emits_the_four_endpoints(tmp_path):
    api = _write(tmp_path)
    assert {p.name for p in api.iterdir()} == {
        "plans.json",
        "permits.json",
        "changes.json",
        "meta.json",
    }
    meta = json.loads((api / "meta.json").read_text())
    assert meta["api_version"] == 1 and meta["generated"] == "2026-11-18"
    assert meta["endpoints"] == ["plans.json", "permits.json", "changes.json"]


def test_v1_never_carries_underscore_fields(tmp_path):
    api = _write(tmp_path)
    for name in ("plans.json", "permits.json", "changes.json"):
        for row in json.loads((api / name).read_text()):
            assert all(not key.startswith("_") for key in row)


def test_unreviewed_fields_stay_dropped(tmp_path):
    api = _write(tmp_path)
    row = json.loads((api / "plans.json").read_text())[0]
    assert "secret_field" not in row and row["pl_number"] == "101-1"


# Section: schema files validate the emitted shape


def _check(instance, schema):
    """Minimal draft-2020-12 subset: type/required/properties/const/items."""
    types = schema.get("type")
    if types:
        if isinstance(types, str):
            types = [types]
        pytypes = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
        }
        ok = False
        for t in types:
            if (
                t == "null"
                and instance is None
                or t in pytypes
                and isinstance(instance, pytypes[t])
            ):
                ok = True
        assert ok, f"{instance!r} not of type {types}"
    if "const" in schema:
        assert instance == schema["const"]
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            assert key in instance, f"missing {key}"
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in instance:
                _check(instance[key], sub)
    if isinstance(instance, list) and "items" in schema:
        for item in instance:
            _check(item, schema["items"])


def test_emitted_payloads_validate_against_their_schemas(tmp_path):
    api = _write(tmp_path)
    for name in ("plans", "permits", "changes", "meta"):
        schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())
        instance = json.loads((api / f"{name}.json").read_text())
        _check(instance, schema)


def test_schema_files_exist_and_parse():
    assert {p.name for p in SCHEMA_DIR.iterdir()} == {
        "plans.schema.json",
        "permits.schema.json",
        "changes.schema.json",
        "meta.schema.json",
    }
