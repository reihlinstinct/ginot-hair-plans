"""Synthetic fixtures only: never copy actual sensitive municipal responses."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).parents[1] / "scripts/vpn/permit_publication_probe.py"
spec = importlib.util.spec_from_file_location("publication_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_process_keeps_dates_not_html_notes_staff_or_payment():
    row = {
        "processCode": 12,
        "stepCode": 800,
        "execDateStr": "04/11/2026",
        "planDateStr": "13/12/2026",
        "total": "<b>PRIVATE_PAYER</b>",
        "hearot": "PRIVATE_NOTES",
        "achraTik": "PRIVATE_STAFF",
        "newSchemaField": {"secret": "PRIVATE_NESTED"},
        "stepCodeText": "PRIVATE_LABEL",
    }
    assert probe.sanitize([row], "process_content_242700451") == [
        {
            "processCode": 12,
            "stepCode": 800,
            "execDateStr": "04/11/2026",
            "planDateStr": "13/12/2026",
        }
    ]


def test_all_routes_fail_closed_for_unknown_nested_or_nonfinite_values():
    for tag, fields in probe.PUBLIC_FIELDS.items():
        for bad in [
            {"secret": "PRIVATE"},
            ["PRIVATE"],
            True,
            float("nan"),
            float("inf"),
        ]:
            row = {key: bad for key in fields}
            assert probe.sanitize([row], tag) == [{}]
        assert probe.sanitize(["PRIVATE", None, 42], tag) == []
    assert probe.sanitize([{"unknown": "PRIVATE"}], "new_procedure") == [{}]


def test_bounded_values_not_raw_truncation():
    assert probe.sanitize([{"rehovName": "PRIVATE" * 2000}], "address_242700455") == [
        {}
    ]
    assert probe.sanitize([{"rehovName": "<b>PRIVATE</b>"}], "address_242700455") == [
        {}
    ]
    assert probe.sanitize(
        [{"execDateStr": "04/11/2026 PRIVATE"}], "process_content_242700451"
    ) == [{}]
    assert len(probe.sanitize([{}] * 1001, "address_242700455")) == 1000


def test_public_address_and_case_status_survive():
    assert probe.sanitize(
        [
            {
                "tikNum": "1983/0461.03",
                "rehovName": "רמבן",
                "mispBait": "24",
                "schunaName": "רחביה",
                "cordinataX": 220378,
                "cordinataY": 631339,
                "mispDira": "PRIVATE",
            }
        ],
        "address_242700455",
    ) == [
        {
            "tikNum": "1983/0461.03",
            "rehovName": "רמבן",
            "mispBait": "24",
            "schunaName": "רחביה",
            "cordinataX": 220378,
            "cordinataY": 631339,
        }
    ]
    assert probe.sanitize(
        [
            {
                "statusCode": 28000124,
                "fullTaarihStatus": "04/11/2026",
                "mahutBakasha": "PRIVATE",
            }
        ],
        "details_242700447",
    ) == [{"statusCode": 28000124, "fullTaarihStatus": "04/11/2026"}]


def test_call_serializes_only_projection(monkeypatch, tmp_path, capsys):
    import builtins

    body = tmp_path / "synthetic.json"
    body.write_text(
        json.dumps(
            [
                {
                    "stepCode": 800,
                    "execDateStr": "04/11/2026",
                    "total": "<span>PRIVATE_PAYER</span>",
                    "achraTik": "PRIVATE_STAFF",
                    "future": {"payment": "PRIVATE_FUTURE"},
                }
            ]
        )
    )
    real_open = builtins.open
    monkeypatch.setattr(
        builtins,
        "open",
        lambda path, *a, **k: real_open(
            body if path == "/tmp/permit_pub_body" else path, *a, **k
        ),
    )
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="200\tapplication/json\t500"),
    )
    assert probe.call("process_content_242700451", 242700451, {}) == 0
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    assert json.loads(output)["rows"] == [
        {"stepCode": 800, "execDateStr": "04/11/2026"}
    ]
