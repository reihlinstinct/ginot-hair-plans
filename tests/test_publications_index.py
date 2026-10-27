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


def test_publication_projection_written_and_committed_with_index(tmp_path, monkeypatch):
    import json

    import pytest

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('publish_projection', root / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'data/publications_active.json').write_text(json.dumps([
        {'tik_num': '2026/0439.00', 'in_polygon': True,
         'objection_deadline': '2026-11-13', 'private_note': 'omit'}]))
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    def stop_before_network(*args, **kwargs):
        raise RuntimeError('network boundary reached')
    monkeypatch.setattr(module, 'gh', stop_before_network)
    with patch.object(module.subprocess, 'run') as run, pytest.raises(
            RuntimeError, match='network boundary reached'):
        module.main()
    assert run.call_args_list == [
        ((['python3', 'scripts/build_site_index.py', 'data', 'docs/index.json'],), {'check': True}),
        ((['python3', 'scripts/render_permits_page.py', '--default-only'],), {'check': True})]
    projection = json.loads((tmp_path / 'docs/publications_active.json').read_text())
    assert projection == [{'tik_num': '2026/0439.00', 'in_polygon': True,
                           'objection_deadline': '2026-11-13', 'publication_date': None}]
    assert {'docs/publications_active.json', 'docs/index.json'} <= set(module.FILES)
