"""Synthetic privacy injection at the public JSON boundary (#123)."""

import json

from ginot import page
from ginot.public_api import PUBLIC_API_FIELDS, project


def test_unknown_fields_and_nested_values_fail_closed():
    for kind in PUBLIC_API_FIELDS:
        assert project([{"future_private": "SYNTHETIC_SECRET"}], kind) == [{}]
        for bad in [{"secret": "SYNTHETIC_SECRET"}, ["SYNTHETIC_SECRET"], float("inf")]:
            assert project([{k: bad for k in PUBLIC_API_FIELDS[kind]}], kind) == [{}]
    assert project([{"pl_number": "123"}], "unknown") == [{}]


def test_rendered_json_drops_injected_private_fields(tmp_path):
    secret = "SYNTHETIC_PRIVATE_SENTINEL"
    private = {
        "baaleiInyanList": secret,
        "phone": secret,
        "national_id": secret,
        "planner_note": secret,
        "tracking_state": secret,
        "future_private": secret,
    }
    rows = [
        {
            "pl_number": "101-1",
            "pl_name": "Public plan",
            "station_desc": "הפקדה",
            "pl_area_dunam": 1,
            "mavat_url": "https://mavat.iplan.gov.il/example",
            "receiving_date": "",
            "depositing_date": "",
            "inside_flag": "inside",
            "objection_deadline_derived_60d_from_publication": "",
            **private,
        }
    ]
    changes = [
        {
            "pl_number": "101-1",
            "pl_name": "Public plan",
            "mavat_url": "https://mavat.iplan.gov.il/example",
            "kind": "new",
            **private,
        }
    ]
    permits = tmp_path / "permits.json"
    permits.write_text(
        json.dumps({"requests": [{"tik_num": "2026/0001.01", **private}]})
    )
    page.render_site(rows, changes, str(tmp_path), permits_path=str(permits))
    for filename in ["data.json", "open.json"]:
        text = (tmp_path / filename).read_text()
        assert secret not in text
        value = json.loads(text)
        for kind in ["rows", "changes", "permits", "plans"]:
            for row in value.get(kind, []):
                assert set(row) <= set(PUBLIC_API_FIELDS[kind])
    assert (
        json.loads((tmp_path / "data.json").read_text())["rows"][0]["pl_number"]
        == "101-1"
    )
