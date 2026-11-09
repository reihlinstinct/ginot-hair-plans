"""The repo layout contract holds (issue #721).

The checker is the executable contract; these tests pin its semantics:
required community-standards files exist, no code at the repository root,
every top-level directory listed, per-directory type allowlists enforced.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "ci" / "check_repo_layout.py"


# Section: Isolated repository fixtures


@pytest.fixture(autouse=True)
def isolate_git_environment(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("layout_checker", CHECKER)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    for key in checker.GIT_LOCATION_VARIABLES:
        monkeypatch.delenv(key, raising=False)


def run_checker():
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )


# Section: Repository contract checks


def test_repo_layout_conforms():
    result = run_checker()
    assert result.returncode == 0, result.stdout


def test_no_python_at_repository_root():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    root_py = [p for p in tracked if "/" not in p and p.endswith(".py")]
    assert root_py == [], f"python files at repository root: {root_py}"


def test_checker_flags_root_python(tmp_path):
    import shutil

    shutil.copy(ROOT / ".repo-layout.yml", tmp_path / ".repo-layout.yml")
    (tmp_path / "stray.py").write_text("# should never live here\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "denied at repository root: stray.py" in result.stdout


def test_checker_flags_missing_required(tmp_path):
    import json

    contract = json.loads((ROOT / ".repo-layout.yml").read_text(encoding="utf-8"))
    contract["required"] = ["DEFINITELY-MISSING.md"]
    contract["root"] = {"allow": ["*"], "deny": []}
    contract["directories"] = {}
    (tmp_path / ".repo-layout.yml").write_text(json.dumps(contract), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "required file missing: DEFINITELY-MISSING.md" in result.stdout


def test_checker_rejects_unlisted_directory_and_wrong_file_type(tmp_path):
    import json

    contract = json.loads((ROOT / ".repo-layout.yml").read_text())
    contract["required"] = []
    (tmp_path / ".repo-layout.yml").write_text(json.dumps(contract))
    (tmp_path / "unplanned").mkdir()
    (tmp_path / "unplanned" / "stray.py").write_text("pass\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "stray.py").write_text("pass\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unlisted top-level directory: unplanned/" in result.stdout
    assert "type not allowed in data/: data/stray.py" in result.stdout


# Section: Workflow and environment boundaries


def test_ci_layout_guard_is_unconditional_and_before_lint():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = [
        job
        for job in workflow["jobs"].values()
        if any(
            step.get("run", "").startswith("ruff check")
            for step in job.get("steps", [])
        )
    ]
    assert jobs
    for job in jobs:
        steps = job["steps"]
        guard = next(
            i
            for i, step in enumerate(steps)
            if step.get("run") == "python scripts/ci/check_repo_layout.py"
        )
        lint = next(
            i
            for i, step in enumerate(steps)
            if step.get("run", "").startswith("ruff check")
        )
        assert guard < lint
        assert "if" not in steps[guard]
        assert "continue-on-error" not in steps[guard]


@pytest.mark.parametrize(
    "filename", ["תכנית מקור עם רווח.pdf", "תכנית מקור\nעם רווח.pdf"]
)
def test_checker_handles_unicode_and_newline_tracked_names(tmp_path, filename):
    import json

    contract = json.loads((ROOT / ".repo-layout.yml").read_text())
    contract["required"] = []
    (tmp_path / ".repo-layout.yml").write_text(json.dumps(contract))
    (tmp_path / "plans").mkdir()
    try:
        (tmp_path / "plans" / filename).write_bytes(b"fixture")
    except OSError:
        if "\n" in filename:
            pytest.skip("filesystem rejects newline filenames")
        raise
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_rejects_unknown_contract_version(tmp_path):
    import json

    (tmp_path / ".repo-layout.yml").write_text(json.dumps({"version": 999}))
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unsupported .repo-layout.yml version" in result.stderr


def test_layout_job_runs_on_all_changes_and_is_in_gate():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["layout"]
    assert "needs" not in job and "if" not in job
    assert "continue-on-error" not in job
    assert any(
        step.get("run") == "python scripts/ci/check_repo_layout.py"
        for step in job["steps"]
    )
    gate = workflow["jobs"]["summary"]
    assert "layout" in gate["needs"]
    assert '"layout"' in gate["steps"][-1]["run"]


@pytest.mark.parametrize(
    "raw",
    [
        '{"version":1,"root":{},"root":{}}',
        '{"version":1,"directories":{"docs":{"allow":[],"allow":["*"]}}}',
    ],
)
def test_checker_rejects_duplicate_policy_keys(tmp_path, raw):
    (tmp_path / ".repo-layout.yml").write_text(raw, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "duplicate layout key" in result.stderr


@pytest.mark.parametrize("nested", [False, True])
def test_checker_rejects_non_repository_or_nested_root(tmp_path, nested):
    import json

    root = tmp_path
    if nested:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        root = tmp_path / "nested"
        root.mkdir()
    (root / ".repo-layout.yml").write_text(
        json.dumps(
            {"version": 1, "required": [], "root": {"allow": ["*"]}, "directories": {}}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "layout root must be the Git top-level directory" in result.stderr


def test_checker_ignores_inherited_git_repository_location(tmp_path):
    import json

    (tmp_path / ".repo-layout.yml").write_text(
        json.dumps(
            {"version": 1, "required": [], "root": {"allow": ["*"]}, "directories": {}}
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    env = dict(
        os.environ,
        GIT_DIR=str(ROOT / ".git"),
        GIT_WORK_TREE=str(ROOT),
        GIT_INDEX_FILE=str(ROOT / ".git/index"),
        GIT_COMMON_DIR=str(ROOT / ".git"),
    )
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_git_environment_preserves_configuration(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("layout_checker", CHECKER)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(ROOT))
    for key in checker.GIT_LOCATION_VARIABLES:
        monkeypatch.setenv(key, "synthetic-location")
    clean = checker.git_environment()
    assert not checker.GIT_LOCATION_VARIABLES.intersection(clean)
    assert clean["GIT_CONFIG_COUNT"] == "1"
    assert clean["GIT_CONFIG_KEY_0"] == "safe.directory"
    assert clean["GIT_CONFIG_VALUE_0"] == str(ROOT)
