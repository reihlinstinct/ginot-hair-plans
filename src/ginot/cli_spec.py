"""Shared argument definitions for the three supported public commands (#720)."""

import argparse

COMMANDS = {
    "ginot-refresh": {
        "entrypoint": "python3 refresh.py",
        "summary": "Refresh public plans and render the static site.",
        "details": "Queries public planning services and writes snapshots, exports and site files. "
        "Run from the repository root with the project dependencies installed. "
        "This command does not file objections.",
        "options": (
            (
                "--council",
                "data/council_ginot_hair.geojson",
                "Council boundary GeoJSON (WGS84).",
            ),
            ("--out", "out", "Directory for generated exports and changes."),
            ("--site", "docs", "Directory for the generated static site."),
            (
                "--base-url",
                "https://reihlinstinct.github.io/ginot-hair-plans/",
                "Public site base URL.",
            ),
            ("--snapshots", "snapshots", "Directory for dated planning snapshots."),
            ("--status", "data/plan_status.json", "Local plan tracking status JSON."),
        ),
    },
    "ginot-land-feed": {
        "entrypoint": "python3 scripts/land_feed.py",
        "summary": "Fetch public Israel Land Authority plan statuses.",
        "details": "Reads plan numbers from the public dataset and tracked plans, queries "
        "the public TabaSearch API and writes status JSON. Requests are paced and repeated "
        "failures abort the run. Run from the repository root; curl must be installed.",
        "options": (
            ("--data-json", "docs/data.json", "Public dataset containing plan rows."),
            (
                "--tracked",
                "data/mavat_tracked_plans.json",
                "Additional tracked plan numbers.",
            ),
            ("--out", "data/land_plan_status.json", "Output status JSON file."),
        ),
    },
    "ginot-mcp-server": {
        "entrypoint": "PYTHONPATH=src python3 -m ginot.mcp_server",
        "summary": "Serve read-only public planning data over MCP stdio.",
        "details": "Reads the public dataset and exchanges JSON-RPC messages over stdin/stdout. "
        "No network requests, writes or private planner files. Objection dates are derived, "
        "not verified official deadlines. Run from the repository root.",
        "options": (("--data", "docs/data.json", "Public dataset to serve."),),
    },
}


def parser_for(command):
    """Build help and parsing from the same definitions as the packaged man pages."""
    spec = COMMANDS[command]
    parser = argparse.ArgumentParser(
        prog=spec["entrypoint"],
        description=spec["summary"],
        epilog=spec["details"],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    for flag, default, help_text in spec["options"]:
        parser.add_argument(flag, default=default, help=help_text)
    return parser


def _roff(text):
    """Escape literal text, including leading roff control characters."""
    return "\\&" + text.replace("\\", r"\e").replace("-", r"\-").replace('"', r"\(dq")


def man_page(command):
    """Return a deterministic section-1 manual; no clock-dependent output."""
    spec = COMMANDS[command]
    lines = [
        f'.TH "{command.upper()}" "1" "" "Ginot HaIr" "User Commands"',
        ".SH NAME",
        _roff(f"{command} - {spec['summary']}"),
        ".SH SYNOPSIS",
        _roff(spec["entrypoint"] + " [OPTIONS]"),
        ".SH DESCRIPTION",
        _roff(spec["details"]),
        ".SH OPTIONS",
        ".TP",
        _roff("-h, --help"),
        _roff("Show command help and exit without performing work."),
    ]
    for flag, default, help_text in spec["options"]:
        lines.extend(
            [".TP", _roff(flag + " VALUE"), _roff(f"{help_text} Default: {default}.")]
        )
    lines.extend(
        [
            ".SH EXIT STATUS",
            _roff(
                "0 on success or --help. Invalid arguments return 2. Runtime failures return nonzero."
            ),
            ".SH NOTES",
            _roff(
                "These manuals document existing Python entrypoints, not installed executable aliases. "
                "Internal CI, maintenance and developer scripts are not part of this manual package."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
