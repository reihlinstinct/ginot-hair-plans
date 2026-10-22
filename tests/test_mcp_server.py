import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ginot import mcp_server as m

ROOT = Path(__file__).resolve().parents[1]
DATA = {"generated": "2026-10-22", "rows": [
    {"pl_number": "A-1", "pl_name": "Alpha", "station_desc": "הפקדה להתנגדויות",
     "objection_deadline_derived_60d_from_publication": "2026-11-05", "private_note": "SECRET"},
    {"pl_number": "B-2", "pl_name": "Beta", "station_desc": "אישור",
     "objection_deadline_derived_60d_from_publication": "2026-11-06"},
    {"pl_number": "C-3", "pl_name": "Gamma", "station_desc": "הפקדה",
     "objection_deadline_derived_60d_from_publication": "bad"}]}


def test_search_and_get_expose_only_public_fields():
    r = m.call_tool(DATA, "search_plans", {"query": "alpha"})
    assert r["total_matches"] == 1 and "private_note" not in json.dumps(r)
    assert m.call_tool(DATA, "get_plan", {"pl_number": "B-2"})["pl_name"] == "Beta"
    with pytest.raises(m.ToolError):
        m.call_tool(DATA, "get_plan", {"pl_number": "nope"})


def test_search_limit_is_clamped():
    rows = [{"pl_number": str(i)} for i in range(80)]
    r = m.call_tool({"rows": rows}, "search_plans", {"limit": 9999})
    assert len(r["plans"]) == 50 and r["total_matches"] == 80


def test_windows_only_deposit_stage_in_range_and_labelled_derived():
    r = m.call_tool(DATA, "upcoming_objection_windows", {"days": 30, "as_of": "2026-10-22"})
    assert [p["pl_number"] for p in r["plans"]] == ["A-1"] and r["plans"][0]["days_left_derived"] == 14
    assert "not a verified official" in r["note"]
    assert m.call_tool(DATA, "upcoming_objection_windows", {"days": 5, "as_of": "2026-10-22"})["plans"] == []
    with pytest.raises(m.ToolError):
        m.call_tool(DATA, "upcoming_objection_windows", {"as_of": "22/10/2026"})


def test_protocol_handshake_list_call_and_errors():
    init = m.handle(DATA, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["capabilities"] == {"tools": {}}
    assert m.handle(DATA, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in m.handle(DATA, {"id": 2, "method": "tools/list"})["result"]["tools"]}
    assert names == {"search_plans", "get_plan", "upcoming_objection_windows", "data_status"}
    bad = m.handle(DATA, {"id": 3, "method": "tools/call", "params": {"name": "delete_all"}})
    assert bad["result"]["isError"] is True
    assert m.handle(DATA, {"id": 4, "method": "resources/write"})["error"]["code"] == -32601


def test_serve_survives_garbage_lines():
    out = io.StringIO()
    m.serve(DATA, io.StringIO('not json\n[]\n\n{"id":1,"method":"ping"}\n'), out)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700 and lines[1]["error"]["code"] == -32700
    assert lines[2]["result"] == {}


def test_real_process_over_stdio_with_real_dataset():
    req = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"data_status","arguments":{}}}\n'
    p = subprocess.run([sys.executable, "-m", "ginot.mcp_server", "--data", str(ROOT / "docs/data.json")],
                       input=req, capture_output=True, text=True, cwd=ROOT, timeout=30, check=False,
                       env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    body = json.loads(json.loads(p.stdout)["result"]["content"][0]["text"])
    assert body["plans"] > 0


def test_loader_rejects_malformed_dataset(tmp_path):
    f = tmp_path / "d.json"
    f.write_text("{}")
    with pytest.raises(TypeError):
        m.load(f)
