"""Synthetic tests for the shared pending-data-PR guard (refs #564).

All GitHub responses are fake; nothing touches the network.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pending_data_pr", ROOT / "scripts/ci/pending_data_pr.py"
)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

REPO = "owner/data-repo"
PREFIX = "weekly-refresh/"


def pr(number, ref, repo=REPO):
    head_repo = None if repo is None else {"full_name": repo}
    return {"number": number, "head": {"ref": ref, "repo": head_repo}}


def fake(pages, calls=None):
    """Fake page fetcher: pages[i] is page i+1 (a list, or a raw string)."""

    def fetch(repo, base, page):
        if calls is not None:
            calls.append((repo, base, page))
        if page > len(pages):
            return "[]"
        body = pages[page - 1]
        if isinstance(body, Exception):
            raise body
        return body if isinstance(body, str) else json.dumps(body)

    return fetch


def test_none_pending():
    assert guard.pending_prs(REPO, PREFIX, fetch=fake([[pr(1, "feature/x")]])) == []


def test_same_repo_matching_prefix_is_pending():
    pages = [[pr(7, "weekly-refresh/20261027"), pr(8, "mavat/20261027")]]
    assert guard.pending_prs(REPO, PREFIX, fetch=fake(pages)) == [7]


def test_fork_with_same_prefix_does_not_count():
    pages = [[pr(9, "weekly-refresh/20261027", repo="someone/fork")]]
    assert guard.pending_prs(REPO, PREFIX, fetch=fake(pages)) == []


def test_deleted_fork_head_repo_null_is_skipped_not_crash():
    pages = [[pr(10, "weekly-refresh/x", repo=None), pr(11, "weekly-refresh/y")]]
    assert guard.pending_prs(REPO, PREFIX, fetch=fake(pages)) == [11]


def test_prefix_must_match_at_start():
    pages = [[pr(12, "fix/weekly-refresh/x")]]
    assert guard.pending_prs(REPO, PREFIX, fetch=fake(pages)) == []


def test_paginates_past_a_full_first_page():
    first = [pr(n, f"other/{n}") for n in range(1, guard.PER_PAGE + 1)]
    second = [pr(500, "weekly-refresh/20261027")]
    calls = []
    found = guard.pending_prs(REPO, PREFIX, fetch=fake([first, second], calls))
    assert found == [500]
    assert [c[2] for c in calls] == [1, 2]


def test_stops_on_short_page_without_extra_request():
    calls = []
    guard.pending_prs(REPO, PREFIX, fetch=fake([[pr(1, "other/1")]], calls))
    assert [c[2] for c in calls] == [1]


def test_too_many_pages_fails_closed(monkeypatch):
    monkeypatch.setattr(guard, "MAX_PAGES", 2)
    full = [pr(n, f"other/{n}") for n in range(guard.PER_PAGE)]
    with pytest.raises(guard.GuardError):
        guard.pending_prs(REPO, PREFIX, fetch=fake([full, full, full]))


@pytest.mark.parametrize(
    "page",
    [
        "not json",
        json.dumps({"message": "Bad credentials"}),
        json.dumps([{"number": 1}]),
        json.dumps([{"number": 1, "head": {"ref": "weekly-refresh/x", "repo": "str"}}]),
        json.dumps(
            [
                {
                    "number": "1",
                    "head": {"ref": "weekly-refresh/x", "repo": {"full_name": REPO}},
                }
            ]
        ),
        json.dumps([None]),
    ],
)
def test_malformed_pages_fail_closed(page):
    with pytest.raises(guard.GuardError):
        guard.pending_prs(REPO, PREFIX, fetch=fake([page]))


def test_empty_prefix_fails_closed():
    with pytest.raises(guard.GuardError):
        guard.pending_prs(REPO, "", fetch=fake([[]]))


def test_main_api_error_exits_nonzero_without_verdict(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    def failing(repo, base, page):
        raise guard.GuardError("gh api failed on page 1 (exit 1)")

    rc = guard.main(["--repo", REPO, "--prefix", PREFIX], fetch=failing)
    assert rc == 1
    assert "pending=" not in capsys.readouterr().out
    assert not out.exists()


def test_main_writes_verdict_to_github_output(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    pages = [[pr(3, "weekly-refresh/a"), pr(2, "weekly-refresh/b")]]
    assert guard.main(["--repo", REPO, "--prefix", PREFIX], fetch=fake(pages)) == 0
    assert out.read_text().splitlines() == ["pending=true", "pending_prs=2 3"]


def test_main_reports_false_when_clear(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert guard.main(["--repo", REPO, "--prefix", PREFIX], fetch=fake([[]])) == 0
    assert out.read_text().splitlines() == ["pending=false", "pending_prs="]


def test_real_fetch_fails_closed_on_gh_error(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(guard.GuardError):
        guard.pending_prs(REPO, PREFIX)


def test_real_fetch_requests_explicit_page_and_base(monkeypatch):
    seen = []

    class Result:
        returncode = 0
        stdout = "[]"

    def run(cmd, **kwargs):
        seen.append(cmd)
        return Result()

    monkeypatch.setattr(guard.subprocess, "run", run)
    assert guard.pending_prs(REPO, PREFIX, base="main") == []
    assert seen == [
        ["gh", "api", f"repos/{REPO}/pulls?state=open&base=main&per_page=100&page=1"]
    ]
