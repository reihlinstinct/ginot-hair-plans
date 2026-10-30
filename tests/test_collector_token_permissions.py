"""#717: read-only defaults; no increase in any existing job's token authority."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "audit-result.yml": ("ingest", {"contents": "write"}),
    "mavat-watch.yml": ("mavat-watch", {"contents": "write"}),
    "mirror-ingest.yml": ("mirror-ingest", {"contents": "write"}),
    "permit-feed.yml": ("permit-feed", {"contents": "write", "pull-requests": "read", "actions": "write"}),
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
    all_jobs = {job: expected, "summary": {"contents": "read"}}
    if name in {"mavat-watch.yml", "mirror-ingest.yml", "permit-feed.yml", "weekly-refresh.yml"}:
        all_jobs["pending"] = {"contents": "read", "pull-requests": "read"}
    if name == "permit-feed.yml":
        all_jobs["publish"] = {"contents": "read", "actions": "read"}
    assert set(wf["jobs"]) == set(all_jobs)
    for other, permissions in all_jobs.items():
        assert wf["jobs"][other].get("permissions", wf["permissions"]) == permissions
    # PR creation keeps its existing independent credential. No GITHUB_TOKEN
    # pull-request write is needed, and no secret or publishing step is added.
    publishers = [step for body in wf["jobs"].values() for step in body["steps"]
                  if "gh pr create" in step.get("run", "")
                  or "scripts/ci/publish_publications.py" in step.get("run", "")]
    assert len(publishers) == 1
    assert publishers[0]["env"]["GH_TOKEN"] == "${{ secrets.REFRESH_DISPATCH_TOKEN }}"
    assert all(body.get("permissions", wf["permissions"]).get("pull-requests") != "write"
               for body in wf["jobs"].values())


def test_checkpoint_pr_lifecycle_read_permission_is_retained():
    workflow = yaml.safe_load((ROOT / ".github/workflows/permit-feed.yml").read_text())
    job = workflow["jobs"]["permit-feed"]
    scan = next(step for step in job["steps"]
                if "--checkpoint --resume" in step.get("run", ""))
    assert scan["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert job["permissions"]["pull-requests"] == "read"
    # Lifecycle checks read PR status before any municipal request.
    source = (ROOT / "scripts/vpn/permit_feed.py").read_text()
    assert "verdict, numbers, cp = lifecycle_gate(" in source
    lifecycle = (ROOT / "scripts/vpn/checkpoint_lifecycle.py").read_text()
    assert "/pulls?state=all" in lifecycle
