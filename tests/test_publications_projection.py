import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ginot.page import render_site

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('content', ['[{', '{}', '[null]', 'null'])
def test_render_ignores_invalid_publications_and_removes_stale_projection(tmp_path, content):
    source = tmp_path / 'input'
    source.mkdir()
    permits = source / 'permit_requests.json'
    permits.write_text('{"requests": []}')
    (source / 'publications_active.json').write_text(content)
    out = tmp_path / 'site'
    out.mkdir()
    (out / 'publications_active.json').write_text('[{"tik_num":"stale"}]')
    render_site([], [], str(out), permits_path=str(permits))
    assert not (out / 'publications_active.json').exists()
    assert (out / 'index.html').exists()


def test_daily_and_site_projection_bytes_identical(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    publications = [{'tik_num': '2026/0439.00', 'in_polygon': True,
                     'objection_deadline': '2026-11-13', 'private_note': 'omit'},
                    {'tik_num': 'outside', 'in_polygon': False, 'objection_deadline': ''}]
    (tmp_path / 'data/publications_active.json').write_text(json.dumps(publications))
    permits = tmp_path / 'data/permit_requests.json'
    permits.write_text('{"requests": []}')
    render_site([], [], str(tmp_path / 'docs'), permits_path=str(permits))
    path = tmp_path / 'docs/publications_active.json'
    site_bytes = path.read_bytes()
    spec = importlib.util.spec_from_file_location('publish_parity', ROOT / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    def stop(*args, **kwargs):
        raise RuntimeError('network boundary')
    monkeypatch.setattr(module, 'gh', stop)
    with patch.object(module.subprocess, 'run'), pytest.raises(RuntimeError, match='network boundary'):
        module.main()
    assert path.read_bytes() == site_bytes
    rows = json.loads(site_bytes)
    assert len(rows) == 2  # Scope preserved, not silently narrowed to in_polygon=true.
    assert all(set(row) == {'tik_num', 'in_polygon', 'objection_deadline', 'publication_date'} for row in rows)


def test_daily_publisher_refuses_invalid_source_before_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'data/publications_active.json').write_text('[{')
    projection = tmp_path / 'docs/publications_active.json'
    projection.write_text('[{"tik_num":"stale"}]')
    spec = importlib.util.spec_from_file_location('publish_invalid', ROOT / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with patch.object(module.subprocess, 'run'), patch.object(module, 'gh') as gh, pytest.raises(
            RuntimeError, match='refusing to publish'):
        module.main()
    gh.assert_not_called()
    assert not projection.exists()


def test_publication_producer_updates_evidence_dependent_subset(tmp_path, monkeypatch):
    """#629: daily evidence must update the same subset as render_site."""
    import subprocess

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    permits = tmp_path / 'data/permit_requests.json'
    permits.write_text(json.dumps({'requests': [
        {'tik_num': '2026/0999.00', 'status': 'שולמה מקדמה', 'address': 'בדיקה 1'}]}))
    publications = tmp_path / 'data/publications_active.json'
    publications.write_text('[]')
    render_site([], [], 'docs', permits_path=str(permits))
    subset = tmp_path / 'docs/permits-default.html'
    assert '2026/0999.00' not in subset.read_text()
    publications.write_text(json.dumps([
        {'tik_num': '2026/0999.00', 'in_polygon': True, 'publication_date': '2026-10-27'}]))
    spec = importlib.util.spec_from_file_location('publish_subset', ROOT / 'scripts/ci/publish_publications.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_run = subprocess.run
    untouched = {p.name: p.read_bytes() for p in (tmp_path / 'docs').iterdir()
                 if p.is_file() and p.name not in {'publications_active.json', 'permits-default.html'}}

    def offline_run(args, **kwargs):
        if args[1] == 'scripts/build_site_index.py':
            return None
        assert args == ['python3', 'scripts/render_permits_page.py', '--default-only']
        return real_run([sys.executable, str(ROOT / args[1]), *args[2:]], **kwargs)

    def stop(*args, **kwargs):
        raise RuntimeError('network boundary')

    import sys
    monkeypatch.setattr(module.subprocess, 'run', offline_run)
    monkeypatch.setattr(module, 'gh', stop)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'synthetic/repo')
    with pytest.raises(RuntimeError, match='network boundary'):
        module.main()
    daily = subset.read_bytes()
    assert '2026/0999.00' in daily.decode()
    render_site([], [], str(tmp_path / 'expected'), permits_path=str(permits))
    assert daily == (tmp_path / 'expected/permits-default.html').read_bytes()
    assert 'docs/permits-default.html' in module.FILES
    assert all((tmp_path / 'docs' / name).read_bytes() == data
               for name, data in untouched.items())
