import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('prepare', Path(__file__).parent.parent / 'scripts/releases/prepare.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_label_driven_semantic_bumps():
    assert release.bump('0.2.0', [{'labels': [{'name': 'bug'}]}]) == '0.2.1'
    assert release.bump('0.2.5', [{'labels': [{'name': 'enhancement'}]}]) == '0.3.0'
    assert release.bump('0.2.5', [{'labels': [{'name': 'breaking'}]}]) == '1.0.0'


def test_preparation_updates_version_notes_changelog_and_footer(tmp_path):
    (tmp_path / 'src/ginot').mkdir(parents=True)
    (tmp_path / 'src/ginot/__init__.py').write_text('__version__ = "0.2.0"')
    (tmp_path / 'CHANGELOG.md').write_text('# Changelog\n')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/index.html').write_text('<p>גרסה <span dir="ltr">0.2.0</span> · Version 0.2.0</p>')
    version = release.prepare(tmp_path, [{'number': 1, 'title': 'Fix example', 'mergedAt': '2026-10-22',
                                        'labels': [{'name': 'bug'}]}], '2026-10-22')
    assert version == '0.2.1'
    notes = (tmp_path / 'releases/0.2.1.md').read_text()
    assert '## עברית' in notes and '## English' in notes and '#1' in notes
    assert '0.2.1' in (tmp_path / 'CHANGELOG.md').read_text()
    assert '0.2.0' not in (tmp_path / 'docs/index.html').read_text()
