"""Explicit public JSON boundary (#123), shared with the read-only Worker.

Only reviewed field names and scalar values can cross this boundary. Adding
fields requires privacy review. This is not a content classifier: free-text
values in approved public fields still require upstream privacy controls.
"""

import json
import math
from pathlib import Path

PUBLIC_API_FIELDS = json.loads(
    (Path(__file__).parent / "static" / "public-api-fields.json").read_text(
        encoding="utf-8"
    )
)


def project(rows, kind):
    """Drop unreviewed fields and nested or non-finite values, fail closed."""
    allowed = PUBLIC_API_FIELDS.get(kind, ())
    return [
        {
            key: value
            for key, value in row.items()
            if key in allowed
            and (
                value is None
                or type(value) in (str, bool, int)
                or (type(value) is float and math.isfinite(value))
            )
        }
        for row in rows
        if isinstance(row, dict)
    ]


API_VERSION = 1


def project_v1(rows, kind):
    """public_project minus underscore-internal fields (#121)."""
    return [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in project(rows, kind)
    ]


def write_v1(out_dir, rows, changes, permits, generated):
    """Write the versioned read-only JSON contract (#121):

    api/v1/plans.json|permits.json|changes.json hold bare public rows;
    api/v1/meta.json carries the version and generation date. Changes
    within v1 are additive only; breaking changes go to v2 side by side.
    data.json stays as a deprecated alias for one release.
    """
    import os

    api_dir = os.path.join(out_dir, "api", "v1")
    os.makedirs(api_dir, exist_ok=True)
    payloads = {
        "plans.json": project_v1(rows, "rows"),
        "changes.json": project_v1(changes, "changes"),
        "permits.json": project_v1(permits, "permits"),
        "meta.json": {
            "api_version": API_VERSION,
            "generated": generated,
            "endpoints": ["plans.json", "permits.json", "changes.json"],
        },
    }
    for name, payload in payloads.items():
        with open(os.path.join(api_dir, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
