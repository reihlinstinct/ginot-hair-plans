"""Explicit public JSON boundary (#123), shared with the read-only Worker.

Only reviewed field names and scalar values can cross this boundary. Adding
fields requires privacy review. This is not a content classifier: free-text
values in approved public fields still require upstream privacy controls.
"""

import json
import math
from pathlib import Path

PUBLIC_API_FIELDS = json.loads(
    (Path(__file__).parent / "static" / "public-api-fields.json").read_text()
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
