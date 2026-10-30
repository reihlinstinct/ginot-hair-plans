"""#717: read-only defaults; no increase in any existing job's token authority."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "audit-result.yml": ("ingest", {"contents": "write"}),
    "mavat-watch.yml": ("mavat-watch", {"contents": "write"}),
    "mirror-ingest.yml": ("mirror-ingest", {"contents": "write"}),
    "permit-feed.yml": ("permit-feed", {"contents": "write", "actions": "write"}),
    "rishui-publish-watch.yml": ("rishui-publish-watch", {
        "contents": "read", "pull-requests": "read", "actions": "read"}),
    "weekly-refresh.yml": ("refresh", {"contents": "write"}),
}


@pytest.mark.parametrize("name,case", CASES.items())
def test_exact_collector_permissions(name, case):
    job, expected = case
    wf = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"][job]["permissions"] == expected
    for other, body in wf["jobs"].items():
        if other != job:
            assert all(value != "write" for value in body.get("permissions", wf["permissions"]).values())
    # PR creation keeps its existing independent credential. No GITHUB_TOKEN
    # pull-request write is needed, and no secret or publishing step is added.
    assert "secrets.REFRESH_DISPATCH_TOKEN" in str(wf["jobs"])
    assert all(body.get("permissions", wf["permissions"]).get("pull-requests") != "write"
               for body in wf["jobs"].values())
