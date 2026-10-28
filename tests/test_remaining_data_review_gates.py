"""#564: callbacks/watchers stage PRs, never bypass review or chain work."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name', ['audit-result.yml', 'mavat-watch.yml', 'mirror-ingest.yml'])
def test_data_workflow_stops_at_reviewed_pr(name):
    workflow = (ROOT / '.github/workflows' / name).read_text()
    assert 'gh pr create' in workflow
    assert 'awaiting independent and exact-head Claude reviews' in workflow
    for forbidden in ('gh pr merge', '--admin', 'gh pr update-branch',
                      '/approve', '/pages/builds', 'gh workflow run',
                      '--force', 'gh run watch', '/merge', 'HEAD:main'):
        assert forbidden not in workflow
    assert 'actions: write' not in workflow
    assert 'pages: write' not in workflow
    if name == 'mavat-watch.yml':
        assert 'if: always()' in workflow
        assert 'python3 scripts/vpn/l2tp.py down' in workflow
    if name == 'audit-result.yml':
        assert 'python3 scripts/audit/ingest.py' in workflow
        assert 'data/parcel_audit.json docs/parcel-audit.json' in workflow
    if name == 'mirror-ingest.yml':
        assert 'scripts/mirror_ingest.py --validate-against' in workflow
        assert 'Dispatch targeted publication-date enrichment' not in workflow
