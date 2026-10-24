"""Read-only MCP server (stdio, JSON-RPC 2.0) over the public plan dataset.

Reads only docs/data.json (already public). No network, no writes, no
planner-private files. Objection dates are derived, not official deadlines.
Run: python -m ginot.mcp_server [--data docs/data.json]
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from .dates import today_il

PROTOCOL = "2024-11-05"
DERIVED_NOTE = (
    "Derived from publication dates (60 days); not a verified official "
    "deadline. Check the plan's source page before relying on it."
)
PUBLIC_FIELDS = (
    "pl_number",
    "pl_name",
    "station_desc",
    "internet_short_status",
    "entity_subtype_desc",
    "receiving_date",
    "open_date",
    "depositing_date",
    "pl_last_deposit_date",
    "objection_deadline_derived_60d_from_publication",
    "pl_area_dunam",
    "mavat_url",
    "last_update_date",
    "land_status",
    "land_status_date",
)

TOOLS = [
    {
        "name": "search_plans",
        "description": "Search public plans by text in number/name/status/type. Returns at most `limit` rows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "get_plan",
        "description": "Get one public plan by pl_number.",
        "inputSchema": {
            "type": "object",
            "properties": {"pl_number": {"type": "string"}},
            "required": ["pl_number"],
        },
    },
    {
        "name": "upcoming_objection_windows",
        "description": "Plans whose DERIVED objection window ends within N days from as_of (default today). "
        + DERIVED_NOTE,
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 0, "maximum": 365},
                "as_of": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    },
    {
        "name": "data_status",
        "description": "Dataset generation date and plan count.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class ToolError(Exception):
    pass


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("rows"), list):
        raise TypeError("dataset has no rows list")
    return data


def public(row):
    return {k: row[k] for k in PUBLIC_FIELDS if k in row}


def call_tool(data, name, args):
    rows = data["rows"]
    if name == "search_plans":
        q = str(args.get("query", "")).strip().lower()
        limit = min(max(int(args.get("limit", 20)), 1), 50)
        hits = [
            r
            for r in rows
            if not q
            or q
            in " ".join(
                str(r.get(k, ""))
                for k in ("pl_number", "pl_name", "station_desc", "entity_subtype_desc")
            ).lower()
        ]
        return {"total_matches": len(hits), "plans": [public(r) for r in hits[:limit]]}
    if name == "get_plan":
        number = str(args.get("pl_number", "")).strip()
        for r in rows:
            if r.get("pl_number") == number:
                return public(r)
        raise ToolError("plan not found")
    if name == "upcoming_objection_windows":
        days = min(max(int(args.get("days", 30)), 0), 365)
        try:
            start = (
                datetime.date.fromisoformat(args["as_of"])
                if args.get("as_of")
                else today_il()
            )
        except ValueError:
            raise ToolError("as_of must be YYYY-MM-DD")
        out = []
        for r in rows:
            raw = r.get("objection_deadline_derived_60d_from_publication")
            try:
                end = datetime.date.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            left = (end - start).days
            if 0 <= left <= days and "הפקדה" in str(r.get("station_desc", "")):
                out.append({**public(r), "days_left_derived": left})
        out.sort(key=lambda r: (r["days_left_derived"], r["pl_number"]))
        return {"as_of": start.isoformat(), "note": DERIVED_NOTE, "plans": out}
    if name == "data_status":
        return {"generated": data.get("generated"), "plans": len(rows)}
    raise ToolError("unknown tool")


def handle(data, msg):
    """Return a response dict, or None for notifications."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok(
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ginot-hair-plans", "version": "0.1.0"},
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            result = call_tool(data, params.get("name"), params.get("arguments") or {})
            return ok(
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                    ]
                }
            )
        except (ToolError, ValueError, TypeError) as e:
            return ok({"isError": True, "content": [{"type": "text", "text": str(e)}]})
    return err(-32601, "method not found")


def serve(data, stdin=sys.stdin, stdout=sys.stdout):
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise TypeError
        except (ValueError, TypeError):
            reply = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
        else:
            reply = handle(data, msg)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="docs/data.json")
    serve(load(ap.parse_args(argv).data))


if __name__ == "__main__":
    main()
