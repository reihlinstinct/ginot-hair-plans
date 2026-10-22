import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ingest', ROOT / 'scripts/audit/ingest.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    body = json.dumps({'batch': {'offset': 400, 'limit': 280}}).encode()
    report = {'schema_version': 1, 'source_commit': 'a' * 40, 'source_run': '1', 'auditor_run': '2',
              'source_digest': hashlib.sha256(body).hexdigest(), 'total_unique_parcels': 4739,
              'published_cursor': 680, 'remaining': 4059, 'warning': '<script>bad</script>'}
    return body, report


def test_ingest_checks_digest_cursor_and_strips_untrusted_strings():
    body, report = fixture()
    result = module.validate(report, body, body)
    assert result['published_cursor'] == 680 and result['remaining'] == 4059
    assert '<script>' not in json.dumps(result)


@pytest.mark.parametrize('key,value', [('source_digest', 'bad'), ('published_cursor', 100),
                                      ('source_commit', 'main; bad'), ('total_unique_parcels', 0)])
def test_reject_bad_callback(key, value):
    body, report = fixture()
    report[key] = value
    with pytest.raises(ValueError):
        module.validate(report, body, body)


def test_reject_stale_snapshot():
    body, report = fixture()
    with pytest.raises(ValueError, match='Stale'):
        module.validate(report, body, b'{"changed":true}')


def test_handshake_cannot_loop_or_dispatch_scan():
    callback = (ROOT / '.github/workflows/audit-result.yml').read_text()
    assert 'permit-feed.yml' not in callback and 'gh workflow run' not in callback
    assert 'data/backfill_request.json' not in callback
    scan = (ROOT / '.github/workflows/permit-feed.yml').read_text()
    assert "env.REQ_MODE != 'enrich'" in scan
    assert 'Dispatch read-only Go auditor after scan publication' in scan
