"""Mirror script import contracts from outside the repository working directory."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mirror_ingest.py"


def _run(tmp_path, args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_direct_script_help_outside_repository(tmp_path):
    result = _run(tmp_path, [str(SCRIPT), "--help"])
    assert result.returncode == 0, result.stderr
    assert "--allow-empty" in result.stdout
    assert "--pending" in result.stdout


def test_file_import_keeps_helper_exports_outside_repository(tmp_path):
    code = f"""
import importlib.util
spec = importlib.util.spec_from_file_location('isolated_mirror', {str(SCRIPT)!r})
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)
assert mirror.diff_records([], [{{'tik_num': '1'}}]) == {{
    'new_tiks': ['1'], 'changed_tiks': [], 'gone_tiks': []}}
assert mirror._iso_min('2026-01-02', '2026-01-01') == '2026-01-01'
assert mirror.content_marker([]).startswith('sha256:')
assert mirror.ENRICHED_FIELDS == ('publication_start', 'publication_end_planned')
assert 'הבקשה נסגרה' in mirror.TERMINAL_STATUSES
"""
    result = _run(tmp_path, ["-c", code])
    assert result.returncode == 0, result.stderr
