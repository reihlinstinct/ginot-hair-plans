"""The VPN-only feed must prepare the parcel renderer before network work."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_feed_installs_geometry_and_smoke_checks_renderer_before_tunnel():
    workflow = (ROOT / '.github/workflows/permit-feed.yml').read_text()
    install = workflow.index('pip install --only-binary=:all: -r requirements.txt')
    smoke = workflow.index('python3 scripts/render_permits_page.py --check-dependencies')
    tunnel = workflow.index('- name: Bring up owner-operated L2TP/IPsec tunnel')
    assert install < smoke < tunnel
    assert 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0' in workflow
    assert 'python-version: "3.12"' in workflow


def test_dependency_preflight_never_reads_or_writes_data(tmp_path):
    import subprocess
    import sys

    # Fail on attempted reads as well as writes, including absolute paths.
    # runpy preserves the real script import path and command-line behavior.
    probe = r"""
import os, runpy, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'scripts'))
sys.argv = [str(root / 'scripts/render_permits_page.py'), '--check-dependencies']
blocked = [root / 'data', root / 'docs', Path.cwd() / 'data', Path.cwd() / 'docs']
hits = []
def audit(event, args):
    if event not in ('open', 'os.listdir', 'os.scandir') or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = Path(os.fsdecode(args[0])).resolve()
    if any(path == base or base in path.parents for base in blocked):
        hits.append(str(path))
        raise AssertionError(f'preflight attempted data I/O: {path}')
sys.addaudithook(audit)
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
finally:
    if hits:
        os._exit(3)
"""
    result = subprocess.run([sys.executable, '-B', '-c', probe, str(ROOT)],
                            check=False, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_checkout_does_not_leave_credentials_for_dependency_code():
    workflow = (ROOT / '.github/workflows/permit-feed.yml').read_text()
    checkout = workflow.split('- uses: actions/checkout@', 1)[1].split('- name:', 1)[0]
    assert 'persist-credentials: false' in checkout
    # #567: the renderer job fetches main anonymously and never enables git
    # auth; only the isolated publish job does, right before its push.
    prepare = workflow.split('- name: Prepare publication commit', 1)[1].split('- name:', 1)[0]
    assert 'git fetch origin main' in prepare
    assert 'gh auth' not in prepare and 'secrets.' not in prepare
    publish = workflow.split('- name: Publish changes as a PR', 1)[1]
    assert publish.index('gh auth setup-git') < publish.index('git push -u origin')


def test_git_auth_is_only_enabled_after_dependency_preflight():
    workflow = (ROOT / '.github/workflows/permit-feed.yml').read_text()
    import yaml
    steps = yaml.safe_load(workflow)['jobs']['permit-feed']['steps']
    assert sum('actions/checkout@' in s.get('uses', '') for s in steps) == 1
    assert workflow.count('gh auth setup-git') == 1
    assert workflow.index('gh auth setup-git') > workflow.index('--check-dependencies')
    assert workflow.index('gh auth setup-git') > workflow.index('- name: Publish changes as a PR')


def test_publication_watch_prepares_renderer_before_any_network_work():
    workflow = (ROOT / '.github/workflows/rishui-publish-watch.yml').read_text()
    install = workflow.index('pip install --only-binary=:all: -r requirements.txt')
    smoke = workflow.index('python3 scripts/render_permits_page.py --check-dependencies')
    reuse = workflow.index('- name: Reuse verified probe output without fetching')
    assert install < smoke < workflow.index('scripts/vpn/l2tp.py up')
    assert smoke < workflow.index('scripts/ci/publish_publications.py')
    assert 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0' in workflow
    assert 'python-version: "3.12"' in workflow
    assert smoke < reuse
    checkout = workflow.split('- uses: actions/checkout@', 1)[1].split('- uses:', 1)[0]
    assert 'persist-credentials: false' in checkout


def test_publication_dependency_command_uses_yaml_block_scalar():
    # The colon-space in --only-binary=:all: -r must not be a plain scalar.
    workflow = (ROOT / '.github/workflows/rishui-publish-watch.yml').read_text()
    install = workflow.split('- name: Install publication renderer dependencies', 1)[1].split('- name:', 1)[0]
    assert 'run: |\n          pip install --only-binary=:all: -r requirements.txt' in install
