"""One byte-stable writer for public publication metadata projections."""
import json
from pathlib import Path

PUBLIC_FIELDS = ('tik_num', 'objection_deadline', 'in_polygon')


def write_projection(source, destination):
    """Write allowlisted public fields, clearing stale output if unavailable.

    Preserve all normalized rows. Scope filtering belongs to the consumer,
    not this serialization helper. Invalid JSON or structure is unavailable,
    not an empty but successful projection.
    """
    destination = Path(destination)
    try:
        rows = json.loads(Path(source).read_text(encoding='utf-8'))
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError('publication source must be a list of objects')
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError, ValueError):
        destination.unlink(missing_ok=True)
        return False
    content = [{key: row.get(key) for key in PUBLIC_FIELDS} for row in rows]
    destination.write_text(json.dumps(content, ensure_ascii=False) + '\n', encoding='utf-8')
    return True
