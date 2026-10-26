from pathlib import Path


def test_watch_uses_checked_text_only_pr_and_preserves_outputs():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/rishui-publish-watch.yml").read_text()
    script = (root / "scripts/ci/publish_publications.py").read_text()
    assert "git push" not in workflow
    assert "REFRESH_DISPATCH_TOKEN" in workflow
    assert "publish_publications.py" in workflow
    assert "data/publications_active.json" in workflow.split("path: |")[1]
    assert "/tmp/publish-new.json" in workflow.split("path: |")[1]
    assert "reuse_probe_run_id" in workflow
    assert "git/trees" in script
    assert "if checks and all" in script
    assert "--match-head-commit" in script
    assert "FAILURE" in script
