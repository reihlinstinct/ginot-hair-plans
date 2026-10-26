from pathlib import Path


def test_publication_update_rebuilds_and_commits_index():
    script = (Path(__file__).resolve().parents[1] / "scripts/ci/publish_publications.py").read_text()
    assert "'docs/index.json'" in script
    assert "'scripts/build_site_index.py', 'data', 'docs/index.json'" in script
    assert "check=True" in script
