"""The VPN script stays importable outside the checkout without root or network."""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "vpn" / "l2tp.py"


def test_isolated_file_import_preserves_validation_and_root_guard(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    code = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('isolated_l2tp', {str(SCRIPT)!r})
l2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2tp)
try:
    l2tp.quote('')
except l2tp.TunnelError:
    pass
else:
    raise AssertionError('credential validation exception identity changed')
assert l2tp.summarize_negotiation('unclassified input')['classes'] == []
assert not any(l2tp.established_snapshot('').values())
l2tp.os.geteuid = lambda: 1000
try:
    l2tp.main()
except SystemExit as exc:
    assert str(exc) == 'VPN helper requires the disposable Ubuntu runner sudo context'
else:
    raise AssertionError('root guard did not stop execution')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
