"""Badge endpoint generation tests (issue #439): invalid metrics must raise."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "publish_badges", ROOT / "scripts/ci/publish_badges.py"
)
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

JUNIT = """<testsuite><testcase classname="a" name="t1"/>
<testcase classname="a" name="t2"><skipped/></testcase>
<testcase classname="a" name="t3"/></testsuite>"""


def test_python_metrics_happy_path():
    cov = json.dumps({"totals": {"percent_covered": 81.234}})
    out = pb.metrics("python", JUNIT, cov)
    assert out["tests"]["message"] == "2 passed, 1 skipped"
    assert out["coverage"]["message"] == "81.2%"
    assert out["tests"]["schemaVersion"] == 1


def test_python_metrics_rejects_failing_and_empty():
    cov = json.dumps({"totals": {"percent_covered": 50}})
    with pytest.raises(ValueError):
        pb.metrics("python", "<testsuite/>", cov)
    failing = '<testsuite><testcase name="x"><failure/></testcase></testsuite>'
    with pytest.raises(ValueError):
        pb.metrics("python", failing, cov)
    with pytest.raises(ValueError):
        pb.metrics("python", JUNIT, json.dumps({"totals": {"percent_covered": 140}}))


def test_go_metrics_from_json_lines():
    lines = "\n".join([
        json.dumps({"Action": "pass", "Test": "TestA"}),
        json.dumps({"Action": "skip", "Test": "TestB"}),
        json.dumps({"Action": "pass", "Test": "TestA"}),  # duplicate keeps last state
        json.dumps({"Action": "output", "Test": "TestC"}),  # ignored action
    ])
    out = pb.metrics("go", lines, "coverage: 72.5% of statements")
    assert out["tests"]["label"] == "Go suite"
    assert out["tests"]["message"] == "1 passed, 1 skipped"
    assert out["coverage"]["message"] == "72.5%"


def test_go_metrics_missing_coverage_raises():
    with pytest.raises(ValueError, match="Missing measured coverage"):
        pb.metrics("go", '{"Action":"pass","Test":"T"}', "no percentage here")


def test_main_writes_badge_files(tmp_path):
    import subprocess
    import sys

    res = tmp_path / "r.xml"
    res.write_text(JUNIT)
    cov = tmp_path / "c.json"
    cov.write_text(json.dumps({"totals": {"percent_covered": 90}}))
    outdir = tmp_path / "badges"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/publish_badges.py"),
         "python", str(res), str(cov), str(outdir)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    tests_badge = json.loads((outdir / "tests.json").read_text())
    coverage_badge = json.loads((outdir / "coverage.json").read_text())
    assert tests_badge["color"] == "brightgreen"
    assert coverage_badge["message"] == "90.0%"


def test_push_badges_recovers_from_racing_push(tmp_path):
    """Issue #497: a concurrent badge-data push must not fail the run.

    A git shim injects a competing commit and rejects the script's first
    push with the real "cannot lock ref" error; the script must re-fetch,
    re-apply its measured files on top, and push successfully.
    """
    import os
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git:
        pytest.skip("git not available")

    def run(args, cwd=None, env=None):
        return subprocess.run(
            args, cwd=cwd, env=env, capture_output=True, text=True, check=True
        )

    bare = tmp_path / "remote.git"
    run([git, "init", "--bare", str(bare)])
    seed = tmp_path / "seed"
    seed.mkdir()
    run([git, "init"], cwd=seed)
    run([git, "config", "user.name", "t"], cwd=seed)
    run([git, "config", "user.email", "t@t"], cwd=seed)
    run([git, "switch", "--orphan", "badge-data"], cwd=seed)
    (seed / "tests.json").write_text('{"old": 1}\n')
    (seed / "coverage.json").write_text('{"old": 1}\n')
    run([git, "add", "."], cwd=seed)
    run([git, "commit", "-m", "seed badges"], cwd=seed)
    run([git, "remote", "add", "origin", str(bare)], cwd=seed)
    run([git, "push", "origin", "badge-data"], cwd=seed)

    work = tmp_path / "work"
    work.mkdir()
    run([git, "init"], cwd=work)
    run([git, "remote", "add", "origin", str(bare)], cwd=work)

    badges = tmp_path / "badges"
    badges.mkdir()
    (badges / "tests.json").write_text('{"new": 1}\n')
    (badges / "coverage.json").write_text('{"new": 1}\n')

    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        """#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "push" ] && [ ! -f "$SHIM_DIR/pushed-once" ]; then
    touch "$SHIM_DIR/pushed-once"
    COMP="$SHIM_DIR/competitor"
    mkdir -p "$COMP"
    "$REAL_GIT" -C "$COMP" init -q
    "$REAL_GIT" -C "$COMP" config user.name t
    "$REAL_GIT" -C "$COMP" config user.email t@t
    "$REAL_GIT" -C "$COMP" fetch -q "$SHIM_REMOTE" badge-data
    "$REAL_GIT" -C "$COMP" checkout -q -b badge-data FETCH_HEAD
    echo '{"other": 1}' > "$COMP/tests.json"
    "$REAL_GIT" -C "$COMP" add tests.json
    "$REAL_GIT" -C "$COMP" commit -q -m 'competing badge push'
    "$REAL_GIT" -C "$COMP" push -q "$SHIM_REMOTE" badge-data
    echo ' ! [remote rejected] HEAD -> badge-data (cannot lock ref)' >&2
    exit 1
  fi
done
exec "$REAL_GIT" "$@"
"""
    )
    shim.chmod(0o755)

    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "REAL_GIT": git,
            "SHIM_DIR": str(shim_dir),
            "SHIM_REMOTE": str(bare),
        }
    )
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/push_badges.sh"), str(badges)],
        check=False,
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "re-fetching and re-applying" in proc.stderr

    run([git, "fetch", "origin", "badge-data"], cwd=work)
    out = run(
        [git, "show", "origin/badge-data:tests.json"], cwd=work
    ).stdout.strip()
    assert out == '{"new": 1}'
    log = run(
        [git, "log", "--format=%s", "origin/badge-data"], cwd=work
    ).stdout
    assert "data: measured successful main CI badges" in log
    assert "competing badge push" in log  # retry built on the winner's commit


def test_push_badges_fails_loud_when_staging_breaks(tmp_path):
    """publish() runs in condition context, where set -e is suppressed:
    a failing cp/add/commit must abort the run, not exit 0 as
    'nothing new' (review on #497's fix)."""
    import os
    import shutil
    import subprocess

    git = shutil.which("git")
    if not git:
        pytest.skip("git not available")

    def run(args, cwd=None):
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)

    bare = tmp_path / "remote.git"
    run([git, "init", "--bare", str(bare)])
    seed = tmp_path / "seed"
    seed.mkdir()
    run([git, "init"], cwd=seed)
    run([git, "config", "user.name", "t"], cwd=seed)
    run([git, "config", "user.email", "t@t"], cwd=seed)
    run([git, "switch", "--orphan", "badge-data"], cwd=seed)
    (seed / "tests.json").write_text('{"old": 1}\n')
    (seed / "coverage.json").write_text('{"old": 1}\n')
    run([git, "add", "."], cwd=seed)
    run([git, "commit", "-m", "seed badges"], cwd=seed)
    run([git, "remote", "add", "origin", str(bare)], cwd=seed)
    run([git, "push", "origin", "badge-data"], cwd=seed)

    work = tmp_path / "work"
    work.mkdir()
    run([git, "init"], cwd=work)
    run([git, "remote", "add", "origin", str(bare)], cwd=work)

    badges = tmp_path / "badges"
    badges.mkdir()
    (badges / "tests.json").write_text('{"new": 1}\n')
    (badges / "coverage.json").write_text('{"new": 1}\n')

    # git shim: every `add` fails -> the old script masked this as a
    # clean-index exit 0; the fixed script must fail loudly.
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        """#!/usr/bin/env bash
seen_add=""
seen_coverage=""
for a in "$@"; do
  [ "$a" = "add" ] && seen_add=1
  [ "$a" = "coverage.json" ] && seen_coverage=1
done
if [ -n "$seen_add" ] && [ -n "$seen_coverage" ]; then
  echo "fatal: simulated index failure" >&2
  exit 1
fi
exec "$REAL_GIT" "$@"
"""
    )
    shim.chmod(0o755)

    env = dict(os.environ)
    env.update({"PATH": f"{shim_dir}:{os.environ['PATH']}", "REAL_GIT": git})
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts/ci/push_badges.sh"), str(badges)],
        check=False,
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "badge git add failed" in proc.stderr
