"""Publication-cleanliness gate tests (issue #874).

Each test builds a synthetic git repository: the publication commit is
already made, and the check must catch whatever docs/ state it left
behind - modified, deleted or untracked - while ignoring the rest of
the tree. No network; git is the only external command.
"""

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_publication_clean", ROOT / "scripts/ci/check_publication_clean.py"
)
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    (repo / "docs" / "index.html").write_text("v1\n")
    (repo / "docs" / "permits.html").write_text("v1\n")
    (repo / "src.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def run_check(repo: Path):
    return subprocess.run(
        [
            cpc.sys.executable,
            str(ROOT / "scripts/ci/check_publication_clean.py"),
            "--root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


# Section: Clean publication bundles pass


def test_clean_tree_passes(tmp_path):
    repo = make_repo(tmp_path)
    result = run_check(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout


def test_changes_outside_docs_are_ignored(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "src.py").write_text("x = 2\n")
    (repo / "new.txt").write_text("untracked outside docs\n")
    result = run_check(repo)
    assert result.returncode == 0, result.stdout + result.stderr


# Section: Leftover covered changes fail early with path evidence


def test_modified_covered_file_fails_with_path(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "index.html").write_text("v2 regenerated\n")
    result = run_check(repo)
    assert result.returncode == 1
    assert "docs/index.html" in result.stdout
    assert "v2 regenerated" not in result.stdout  # paths only, never content


def test_deleted_covered_file_fails_with_path(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "permits.html").unlink()
    result = run_check(repo)
    assert result.returncode == 1
    assert "docs/permits.html" in result.stdout


def test_untracked_rendered_file_fails_with_path(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "feed.xml").write_text("<feed/>\n")
    result = run_check(repo)
    assert result.returncode == 1
    assert "docs/feed.xml" in result.stdout


def test_staged_but_uncommitted_change_fails(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "docs" / "index.html").write_text("v2 staged\n")
    subprocess.run(["git", "add", "docs/index.html"], cwd=repo, check=True)
    result = run_check(repo)
    assert result.returncode == 1
    assert "docs/index.html" in result.stdout
