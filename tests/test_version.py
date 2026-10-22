import re
from pathlib import Path

from ginot import __version__, page

ROOT = Path(__file__).parent.parent


def test_semantic_version_single_source_and_generated_footers():
    assert re.fullmatch(r'\d+\.\d+\.\d+', __version__)
    for html in [page.render_index([], [], '2026-10-22', 'test'),
                 page.render_about('2026-10-22', 'test'),
                 page.render_review('101-1', '# test', '2026-10-22', 'test')]:
        assert f'Version {__version__}' in html
        assert html.count('class="site-version"') == 1
    files = [ROOT / 'docs/index.html', ROOT / 'docs/about.html']
    files += list((ROOT / 'docs/reviews').glob('*.html'))
    assert len(files) >= 3
    for file in files:
        assert f'Version {__version__}' in file.read_text(), file


def test_release_notes_have_both_languages_and_changelog():
    notes = (ROOT / f'releases/{__version__}.md').read_text()
    assert '## עברית' in notes and '## English' in notes
    assert __version__ in (ROOT / 'CHANGELOG.md').read_text()
    assert 'Standing authority' in (ROOT / 'releases/README.md').read_text()
