"""Regression (#405): the permit-feed publish step must invoke the permits
fragment renderer and commit the fragment, under set -e - no non-fatal
fallback that could ship a data update with a stale site."""
from pathlib import Path


def test_publish_step_renders_and_commits_permits_fragment():
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-feed.yml"
    ).read_text()
    publish = workflow.split("Publish changes as a PR", 1)[1]
    assert "python3 scripts/render_permits_page.py" in publish
    render_line = next(
        line
        for line in publish.splitlines()
        if "render_permits_page.py" in line and "python3" in line
    )
    assert "||" not in render_line  # no non-fatal fallback: set -e governs
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "docs/permits.html" in add_line

    assert "docs/permit-points.json" in add_line


def test_publish_step_commits_default_permits_subset():
    """#441: the page loads docs/permits-default.html first, so a feed batch
    must commit it with the full fragment or new default rows go stale."""
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-feed.yml"
    ).read_text()
    publish = workflow.split("Publish changes as a PR", 1)[1]
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "docs/permits-default.html" in add_line.split()
