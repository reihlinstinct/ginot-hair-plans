"""Keep the documented search scope narrower than all punctuation (#669)."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_search_help_lists_supported_marks_without_all_punctuation_claim():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    section = text.split('### Table search\n', 1)[1].split('\n### ', 1)[0]
    assert 'however it is punctuated' not in section
    assert 'only the following' in section
    assert 'Commas and other unlisted punctuation are retained' in section


def test_search_normalization_retains_commas():
    source = (ROOT / 'src/ginot/page.py').read_text(encoding='utf-8')
    fn = source.split('_NORM_SEARCH_JS = r"""', 1)[1].split('"""', 1)[0]
    script = fn + '\nconsole.log(JSON.stringify([normSearch("a,b"), normSearch("ab")]));'
    result = subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == ['a,b', 'ab']
