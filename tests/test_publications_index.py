import importlib.util
from pathlib import Path
from unittest.mock import patch


def test_publication_update_rebuilds_and_commits_index():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("publish_index", root / "scripts/ci/publish_publications.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "docs/index.json" in module.FILES
    with patch.object(module.subprocess, "run", side_effect=RuntimeError("stop after build")) as run:
        try:
            module.main()
        except RuntimeError:
            pass
    run.assert_called_once_with(["python3", "scripts/build_site_index.py", "data", "docs/index.json"], check=True)
