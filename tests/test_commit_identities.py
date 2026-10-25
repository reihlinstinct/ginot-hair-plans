"""Regression tests for the commit-identity guard (issue #473).

Incident fixture: 1bfaed94 in PR #432 used instinct@users.noreply.github.com,
which GitHub resolved to the unrelated @instinct account."""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "check_commit_identities", ROOT / "scripts" / "ci" / "check_commit_identities.py"
)
cci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cci)
violations = cci.violations

INCIDENT_EMAIL = "instinct@users.noreply.github.com"
OWNED_NOREPLY = "337939899+reihlinstinct@users.noreply.github.com"
BOT_NOREPLY = "41898282+github-actions[bot]@users.noreply.github.com"


def test_incident_identity_fails_author_and_committer():
    recs = [("1bfaed94" + "0" * 32, INCIDENT_EMAIL, INCIDENT_EMAIL)]
    problems = violations(recs)
    assert len(problems) == 2  # author + committer checked independently
    assert all("'instinct'" in p for p in problems)


def test_incident_identity_fails_when_only_committer():
    recs = [("a" * 40, "reihlinstinct@gmail.com", INCIDENT_EMAIL)]
    problems = violations(recs)
    assert len(problems) == 1 and "committer" in problems[0]


def test_owned_identities_pass():
    recs = [
        ("b" * 40, OWNED_NOREPLY, OWNED_NOREPLY),
        ("c" * 40, "reihlinstinct@gmail.com", BOT_NOREPLY),
        ("d" * 40, "reihl@mail.tab.bot", "49699333+dependabot[bot]@users.noreply.github.com"),
    ]
    assert violations(recs) == []


def test_fork_author_own_noreply_passes_but_stranger_fails():
    fork_rec = [("e" * 40, "octocat@users.noreply.github.com", "someone@example.com")]
    assert violations(fork_rec, fork_author="octocat") == []
    # same commit on an internal PR (no fork author) must fail
    assert len(violations(fork_rec)) == 1
    # a fork PR does NOT license third-party noreply identities
    bad_fork = [("f" * 40, INCIDENT_EMAIL, "x@example.com")]
    assert len(violations(bad_fork, fork_author="octocat")) == 1


def test_non_noreply_emails_pass_by_design():
    recs = [("g" * 40, "agent@instinct.com", "instinct@localhost")]
    assert violations(recs) == []


def test_case_insensitive_username_match():
    recs = [("h" * 40, "ReihlInstinct@users.noreply.github.com", "x@example.com")]
    assert violations(recs) == []


# --- Shallow-history fail-closed tests (CodeRabbit #474 round 2) -------------

import subprocess


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _make_repo(tmp_path):
    """Source repo: main at c1; feature branch adds c2, c3 ON TOP of c1
    (the PR shape: feature = base + new commits)."""
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init", "-q", "-b", "main")
    _git(src, "config", "user.email", "t@example.com")
    _git(src, "config", "user.name", "T")
    (src / "f1.txt").write_text("1")
    _git(src, "add", ".")
    _git(src, "commit", "-q", "-m", "c1")
    _git(src, "checkout", "-q", "-b", "feature")
    for i in (2, 3):
        (src / f"f{i}.txt").write_text(str(i))
        _git(src, "add", ".")
        _git(src, "commit", "-q", "-m", f"c{i}")
    return src


def test_boundary_empty_on_full_history(tmp_path, monkeypatch):
    src = _make_repo(tmp_path)
    clone = tmp_path / "full"
    _git(tmp_path, "clone", "-q", str(src), str(clone))
    _git(clone, "fetch", "-q", "origin", "main:base-ref")
    monkeypatch.chdir(clone)
    # the range must be the two feature commits (non-vacuous check)
    assert len(cci.commit_records("base-ref", "origin/feature")) == 2
    assert cci.boundary_commits("base-ref", "origin/feature") == []


def test_boundary_detected_and_main_fails_closed_on_shallow(tmp_path, monkeypatch, capsys):
    src = _make_repo(tmp_path)
    clone = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", "-b", "feature", f"file://{src}", str(clone))
    _git(clone, "fetch", "-q", "--depth=1", "origin", "main:base-ref")
    monkeypatch.chdir(clone)
    # the range walk sees commits but the history is truncated at the boundary
    assert cci.boundary_commits("base-ref", "HEAD") != []
    rc = cci.main(["--base", "base-ref", "--head", "HEAD"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "shallow boundary" in out


def test_no_merge_base_fails_closed(tmp_path, monkeypatch, capsys):
    """Base truncated ABOVE the branch point while head is complete: no
    merge-base exists, base..head silently includes shared commits, so the
    guard must refuse to pass (CodeRabbit #474 round 4 audit)."""
    src = _make_repo(tmp_path)
    _git(src, "checkout", "-q", "main")
    for i in (2, 3, 4):
        (src / f"m{i}.txt").write_text(str(i))
        _git(src, "add", ".")
        _git(src, "commit", "-q", "-m", f"m{i}")
    clone = tmp_path / "mixed"
    _git(tmp_path, "clone", "-q", "--depth", "2", "-b", "feature", f"file://{src}", str(clone))
    _git(clone, "fetch", "-q", "--deepen=10", "origin", "feature")  # head complete
    _git(clone, "fetch", "-q", "--depth=2", "origin", "main:base-ref")  # base cut above M
    monkeypatch.chdir(clone)
    assert cci.boundary_commits("base-ref", "HEAD") == []  # cut is not head-side
    rc = cci.main(["--base", "base-ref", "--head", "HEAD"])
    assert rc == 1
    assert "no merge-base" in capsys.readouterr().out
