"""Keep the documented search scope narrower than all punctuation (#669)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _node_runtime():
    runtime = shutil.which('node')
    if runtime:
        return runtime
    if os.environ.get('CI'):
        pytest.fail('Node.js is required in CI for search normalization tests')
    pytest.skip('Node.js is not installed; JS search regression skipped locally')


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
    result = subprocess.run([_node_runtime(), '-e', script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == ['a,b', 'ab']


def test_missing_node_skips_local_only(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    monkeypatch.delenv('CI', raising=False)
    with pytest.raises(pytest.skip.Exception, match='Node.js'):
        _node_runtime()


def test_missing_node_fails_ci(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda name: None)
    monkeypatch.setenv('CI', 'true')
    with pytest.raises(pytest.fail.Exception, match='Node.js is required in CI'):
        _node_runtime()


def test_permit_sort_ties_use_tik_num_not_feed_order():
    source = (ROOT / 'src/ginot/page.py').read_text(encoding='utf-8')
    fn = 'function sortRows(){' + source.split('function sortRows(){', 1)[1].split('\n}', 1)[0] + '\n}'
    script = '''
function row(tik, date, rank) {
  return {getAttribute: k => ({'data-tik':tik,'data-pub':date})[k], rank:rank};
}
var rows=[row('2026/0009','2026-10-18',0),row('2026/0002','2026-10-18',0),
 row('2026/0001','2026-10-17',0),row('2026/0008','',1),row('2026/0003','',1),
 row('2026/0007','',2),row('2026/0004','',2)];
function pubRank(r){return r.rank;}
var document={querySelector:()=>null};
''' + fn + '\nsortRows();console.log(JSON.stringify(rows.map(r=>r.getAttribute("data-tik"))));'
    result = subprocess.run([_node_runtime(), '-e', script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [
        '2026/0002', '2026/0009', '2026/0001',
        '2026/0003', '2026/0008', '2026/0004', '2026/0007',
    ]


def test_permit_order_help_qualifies_javascript_cap():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    section = text.split('### Permit ordering', 1)[1].split('### ', 1)[0]
    assert 'With JavaScript enabled, the 20-row cap applies after sorting' in section
    assert 'Without JavaScript' in section
