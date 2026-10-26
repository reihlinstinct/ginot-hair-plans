"""The VPN-only feed must prepare the parcel renderer before network work."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_feed_installs_geometry_and_smoke_checks_renderer_before_tunnel():
    workflow = (ROOT / '.github/workflows/permit-feed.yml').read_text()
    install = workflow.index('pip install "shapely>=2.2.0" "pyproj>=3.8.0"')
    smoke = workflow.index('python3 scripts/render_permits_page.py --check-dependencies')
    tunnel = workflow.index('- name: Bring up owner-operated L2TP/IPsec tunnel')
    assert install < smoke < tunnel
    assert 'actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0' in workflow
    assert 'python-version: "3.12"' in workflow


def test_dependency_preflight_never_reads_or_writes_data(tmp_path):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(ROOT / 'scripts/render_permits_page.py'),
                             '--check-dependencies'], check=False, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
