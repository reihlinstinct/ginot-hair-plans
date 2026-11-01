"""Publication overlay recency-window boundaries (#598, #601, #604).

The overlay predicate and its 90-day policy constant are extracted from the
DEPLOYED source (src/ginot/page.py), never reimplemented here, so the pins
track the real code: 90 days accepted, 91 rejected, same-day (age 0)
accepted, future dates rejected, and only in-polygon valid-dated evidence
qualifies.
"""

import json
import subprocess
from pathlib import Path

from test_search_help import _node_runtime

ROOT = Path(__file__).parent.parent


def _extract(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0].join((start, end))


def _window_fn():
    source = (ROOT / "src/ginot/page.py").read_text(encoding="utf-8")
    parts = [
        _extract(source, "var PUBLICATION_EVIDENCE_MAX_DAYS", ";"),
        _extract(source, "function isoDate(d){", "\n}"),
        _extract(source, "function validIso(v){", "\n}"),
        _extract(source, "function currentEvidence(p){", "\n}"),
    ]
    # The page template is a non-raw Python string, so the source text escapes
    # backslashes; the runtime JS (what the browser runs) has single ones.
    return "\n".join(parts).replace("\\\\", "\\")


_UNSET = object()


def _eval_vector(days_offset, in_polygon=True, date=None, raw=_UNSET):
    if raw is not _UNSET:
        entry = raw
    else:
        d = date
        if d is None:
            import datetime

            dt = datetime.date(2026, 6, 15) - datetime.timedelta(days=days_offset)
            d = dt.isoformat()
        entry = {"in_polygon": in_polygon, "publication_date": d}
    script = (
        "var TODAY='2026-06-15';\n"
        + _window_fn()
        + "\nconsole.log(JSON.stringify([currentEvidence("
        + json.dumps(entry)
        + "), PUBLICATION_EVIDENCE_MAX_DAYS]));"
    )
    result = subprocess.run(
        [_node_runtime(), "-e", script], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def test_exactly_90_days_is_accepted():
    accepted, max_days = _eval_vector(90)
    assert max_days == 90  # policy constant from the deployed source, not a copy
    assert accepted is True


def test_91_days_is_rejected():
    assert _eval_vector(91)[0] is False


def test_same_day_age_zero_is_accepted():
    assert _eval_vector(0)[0] is True


def test_future_publication_date_is_rejected():
    assert _eval_vector(-1)[0] is False


def test_out_of_polygon_evidence_is_rejected():
    assert _eval_vector(5, in_polygon=False)[0] is False


def test_invalid_publication_date_is_rejected():
    assert _eval_vector(0, date="15.06.2026")[0] is False


def test_missing_evidence_is_rejected():
    assert _eval_vector(0, raw=None)[0] is False


def test_truthy_string_in_polygon_is_rejected():
    # #753 review: the guard requires the boolean true, not a truthy value.
    assert _eval_vector(5, in_polygon="yes")[0] is False


def test_numeric_in_polygon_is_rejected():
    assert _eval_vector(5, in_polygon=1)[0] is False
