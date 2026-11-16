"""Post-merge permit router decisions (#565). Synthetic records only."""

import base64
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import permit_router as pr_mod

REPO = "zz-owner/zz-repo"
HEAD, BASE, MERGE, RUN_HEAD, CP = ("a" * 40, "b" * 40, "c" * 40, "d" * 40, "e" * 40)
RUN_ID = 999001


DATA_FILES = [
    "data/permit_scan_provenance.json",
    "data/permits.json",
    "docs/data.json",
    "docs/index.json",
    "docs/permits.html",
    "docs/badge/parcel-zz-1.json",
]


def files(paths=DATA_FILES):
    return [{"filename": path, "status": "modified"} for path in paths]


def pr():
    return {
        "number": 7,
        "merged": True,
        "merge_commit_sha": MERGE,
        "user": {"login": "zz-bot"},
        "changed_files": len(DATA_FILES),
        "head": {
            "ref": "permit-feed/20261029-0300",
            "sha": HEAD,
            "repo": {"full_name": REPO},
        },
        "base": {"ref": "main", "sha": BASE},
    }


def prov(run=str(RUN_ID)):
    return {
        "note": "scan checkpoint binding (issue #566); written by permit_feed.py",
        "checkpoint_commit": CP,
        "batch": {"offset": 280, "limit": 280},
        "source_run": run,
    }


def run():
    return {
        "id": RUN_ID,
        "path": ".github/workflows/permit-feed.yml",
        "repository": {"full_name": REPO},
        "head_repository": {"full_name": REPO},
        "head_branch": "main",
        "event": "schedule",
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": RUN_HEAD,
    }


def reviews():
    return [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}]


class World:
    def __init__(self):
        self.provenance = {
            HEAD: prov(),
            BASE: {**prov("999000"), "checkpoint_commit": "f" * 40},
        }
        self.run = run()
        self.reviews = reviews()
        self.ancestors = {(MERGE, "main"), (RUN_HEAD, BASE)}
        self.markers = ""
        self.files = files()
        self.calls = []

    def read(self, kind, *args):
        self.calls.append((kind, *args))
        if kind == "ancestor":
            return tuple(args) in self.ancestors
        if kind == "provenance":
            return copy.deepcopy(self.provenance.get(args[0]))
        if kind == "run":
            return copy.deepcopy(self.run) if args[0] == RUN_ID else None
        if kind == "reviews":
            return copy.deepcopy(self.reviews)
        if kind == "markers":
            return self.markers
        if kind == "files":
            return copy.deepcopy(self.files)
        raise AssertionError(kind)


def decide(p=None, w=None):
    w = w or World()
    return pr_mod.decide(REPO, p or pr(), w.read)


# Section: Transport


def _gh_world(w, p):
    def gh(path):
        if path == f"repos/{REPO}/pulls/7":
            return p
        if path.startswith(f"repos/{REPO}/compare/"):
            a, b = path.rsplit("/", 1)[1].split("...")
            return {"status": "ahead" if (a, b) in w.ancestors else "diverged"}
        if path.startswith(
            f"repos/{REPO}/contents/data/permit_scan_provenance.json?ref="
        ):
            rec = w.provenance.get(path.rsplit("=", 1)[1])
            return (
                None
                if rec is None
                else {
                    "encoding": "base64",
                    "content": base64.b64encode(json.dumps(rec).encode()).decode(),
                }
            )
        if path == f"repos/{REPO}/actions/runs/{RUN_ID}":
            return w.run
        for prefix, items in (
            (f"repos/{REPO}/pulls/7/reviews", w.reviews),
            (f"repos/{REPO}/issues/7/comments", [{"body": w.markers}]),
            (f"repos/{REPO}/pulls/7/files", w.files),
        ):
            if path.startswith(prefix + "?per_page="):
                return items if int(path.rsplit("page=", 1)[1]) == 1 else []
        return None

    return gh


@pytest.mark.parametrize("which", ["/reviews", "/comments", "/files"])
def test_pagination_budget_exhaustion_stops_instead_of_truncating(which, capsys):
    w, p = World(), pr()
    gh = _gh_world(w, p)
    full = [
        {
            "state": "COMMENTED",
            "commit_id": HEAD,
            "user": {"login": f"zz-{i}"},
            "body": "",
        }
        for i in range(100)
    ]
    assert (
        pr_mod.main(
            ["--repo", REPO, "--pr", "7"],
            gh=lambda path: full if which in path else gh(path),
        )
        == 1
    )
    assert "pagination budget" in capsys.readouterr().out


def _paged(pages_by_prefix):
    """A gh double serving the given pages (1-based) for list endpoints."""

    def gh(path):
        for prefix, pages in pages_by_prefix.items():
            if path.startswith(prefix + "?per_page="):
                page = int(path.rsplit("page=", 1)[1])
                return pages[page - 1] if page <= len(pages) else []
        raise pr_mod.GitHubHTTPError(404)

    return gh


def test_more_than_one_page_of_allowed_files_is_fully_validated():
    w, p = World(), pr()
    many = [
        {"filename": f"docs/badge/parcel-zz-{i}.json", "status": "modified"}
        for i in range(150)
    ]
    w.files = files() + many
    p["changed_files"] = len(w.files)
    gh = _gh_world(w, p)
    files_prefix = f"repos/{REPO}/pulls/7/files"
    paged = _paged({files_prefix: [w.files[:100], w.files[100:]]})

    def gh2(path):
        return paged(path) if path.startswith(files_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 0


def _pad_files(w, p, tail):
    # Page 1 holds exactly PER_PAGE allowed files; the tail lands on page 2.
    w.files = (
        w.files
        + [
            {"filename": f"docs/badge/parcel-zz-{i}.json", "status": "modified"}
            for i in range(100 - len(w.files))
        ]
        + tail
    )
    p["changed_files"] = len(w.files)


def test_rename_source_on_a_later_files_page_is_validated():
    w, p = World(), pr()
    sneaky = [
        {
            "filename": "data/permits.json",
            "status": "renamed",
            "previous_filename": "scripts/ci/permit_router.py",
        }
    ]
    _pad_files(w, p, sneaky)
    gh = _gh_world(w, p)
    files_prefix = f"repos/{REPO}/pulls/7/files"
    paged = _paged({files_prefix: [w.files[:100], w.files[100:]]})

    def gh2(path):
        return paged(path) if path.startswith(files_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1


def test_disallowed_file_on_a_later_page_stops():
    w, p = World(), pr()
    _pad_files(w, p, [{"filename": "src/evil.py", "status": "modified"}])
    gh = _gh_world(w, p)
    files_prefix = f"repos/{REPO}/pulls/7/files"
    paged = _paged({files_prefix: [w.files[:100], w.files[100:]]})

    def gh2(path):
        return paged(path) if path.startswith(files_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1


def test_dedup_marker_on_a_later_comments_page_skips(capsys):
    w, p = World(), pr()
    gh = _gh_world(w, p)
    comments_prefix = f"repos/{REPO}/issues/7/comments"
    filler = [{"body": f"note {i}"} for i in range(100)]
    paged = _paged(
        {comments_prefix: [filler, [{"body": pr_mod.marker(7, HEAD, RUN_ID)}]]}
    )

    def gh2(path):
        return paged(path) if path.startswith(comments_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 0
    assert "skip" in capsys.readouterr().out


def test_decisive_review_on_a_later_page_changes_the_verdict(capsys):
    w, p = World(), pr()
    # Page 1 alone would route (approval at head); page 2 must flip it.
    filler = [
        {"state": "APPROVED", "commit_id": HEAD, "user": {"login": "zz-approver"}}
    ] + [
        {"state": "COMMENTED", "commit_id": HEAD, "user": {"login": f"zz-{i}"}}
        for i in range(99)
    ]
    late = [
        {
            "state": "CHANGES_REQUESTED",
            "commit_id": HEAD,
            "user": {"login": "zz-reviewer"},
        }
    ]
    w.reviews = filler + late
    gh = _gh_world(w, p)
    reviews_prefix = f"repos/{REPO}/pulls/7/reviews"
    paged = _paged({reviews_prefix: [w.reviews[:100], w.reviews[100:]]})

    def gh2(path):
        return paged(path) if path.startswith(reviews_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 0
    assert "verdict=hold" in capsys.readouterr().out


def test_exact_multiple_of_page_size_ends_on_empty_terminal_page():
    w, p = World(), pr()
    w.reviews = [
        {"state": "APPROVED", "commit_id": HEAD, "user": {"login": f"zz-{i}"}}
        for i in range(100)
    ]
    gh = _gh_world(w, p)
    seen = []

    def gh2(path):
        if path.startswith(f"repos/{REPO}/pulls/7/reviews?per_page="):
            seen.append(int(path.rsplit("page=", 1)[1]))
        return gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 0
    assert seen == [1, 2]  # full first page, then the empty terminal page


def test_malformed_later_page_stops():
    w, p = World(), pr()
    gh = _gh_world(w, p)
    reviews_prefix = f"repos/{REPO}/pulls/7/reviews"
    pages = [
        [
            {"state": "COMMENTED", "commit_id": HEAD, "user": {"login": f"zz-{i}"}}
            for i in range(100)
        ],
        {"not": "a list"},
    ]
    paged = _paged({reviews_prefix: pages})

    def gh2(path):
        return paged(path) if path.startswith(reviews_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1


@pytest.mark.parametrize("status", [403, 429, 500, 503])
def test_provenance_http_failures_stop(status):
    def gh(path):
        raise pr_mod.GitHubHTTPError(status)

    with pytest.raises(pr_mod.RouterError):
        pr_mod.github_reader(REPO, gh)("provenance", HEAD)


def test_provenance_absent_only_on_404_with_verified_ref():
    def gh(path):
        if "/contents/" in path:
            raise pr_mod.GitHubHTTPError(404)
        assert path == f"repos/{REPO}/git/commits/{HEAD}"
        return {"sha": HEAD}

    assert pr_mod.github_reader(REPO, gh)("provenance", HEAD) is None


@pytest.mark.parametrize("response", [None, {}, {"sha": BASE}])
def test_provenance_404_with_unverified_ref_stops(response):
    def gh(path):
        if "/contents/" in path:
            raise pr_mod.GitHubHTTPError(404)
        return response

    with pytest.raises(pr_mod.RouterError):
        pr_mod.github_reader(REPO, gh)("provenance", HEAD)


def test_provenance_unreadable_is_not_absent():
    with pytest.raises(pr_mod.RouterError):
        pr_mod.github_reader(REPO, lambda path: None)("provenance", HEAD)


@pytest.mark.parametrize("status", [403, 404, 500, 503])
def test_gh_preserves_http_status(monkeypatch, status):
    import subprocess

    monkeypatch.setattr(
        pr_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 1, f"HTTP/2.0 {status} Error\n\n{{}}", ""
        ),
    )
    with pytest.raises(pr_mod.GitHubHTTPError) as exc:
        pr_mod._gh("test")
    assert exc.value.status == status


@pytest.mark.parametrize("body", ["", "{}", "HTTP/2.0 200 OK\n\nnot-json"])
def test_gh_unreadable_response_stops(monkeypatch, body):
    import subprocess

    monkeypatch.setattr(
        pr_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, body, ""),
    )
    with pytest.raises(pr_mod.RouterError):
        pr_mod._gh("test")


def test_gh_reads_successful_response_and_fails_on_transport_error(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        pr_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 0, 'HTTP/2.0 200 OK\r\n\r\n{"ok":true}', ""
        ),
    )
    assert pr_mod._gh("test") == {"ok": True}

    def unavailable(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(pr_mod.subprocess, "run", unavailable)
    with pytest.raises(pr_mod.RouterError, match="unavailable"):
        pr_mod._gh("test")


@pytest.mark.parametrize(
    "comment", [None, "a string", {"body": None}, {"body": 7}, {"nobody": "x"}]
)
def test_malformed_comment_record_stops_before_dedupe(comment):
    w, p = World(), pr()
    gh = _gh_world(w, p)
    comments_prefix = f"repos/{REPO}/issues/7/comments"

    def gh2(path):
        if path.startswith(comments_prefix + "?per_page="):
            page = int(path.rsplit("page=", 1)[1])
            return [comment] if page == 1 else []
        return gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1


def _allowed_file_pages(n_pages):
    return [
        [
            {"filename": f"docs/badge/parcel-zz-{pg}-{i}.json", "status": "modified"}
            for i in range(100)
        ]
        for pg in range(n_pages)
    ]


def test_exactly_max_full_pages_validate_via_terminal_probe():
    # Five full pages fit the budget exactly: one terminal probe (empty page
    # six) confirms completeness instead of rejecting a valid endpoint.
    w, p = World(), pr()
    p["changed_files"] = 500
    gh = _gh_world(w, p)
    files_prefix = f"repos/{REPO}/pulls/7/files"
    paged = _paged({files_prefix: _allowed_file_pages(5)})

    def gh2(path):
        return paged(path) if path.startswith(files_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 0


def test_max_full_pages_plus_a_full_probe_still_exhausts(capsys):
    # Six full pages means real data sits beyond the budget: fail closed.
    w, p = World(), pr()
    p["changed_files"] = 600
    gh = _gh_world(w, p)
    files_prefix = f"repos/{REPO}/pulls/7/files"
    paged = _paged({files_prefix: _allowed_file_pages(6)})

    def gh2(path):
        return paged(path) if path.startswith(files_prefix) else gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1
    assert "pagination budget" in capsys.readouterr().out


@pytest.mark.parametrize("which", ["/reviews", "/comments", "/files"])
@pytest.mark.parametrize("bad_page", [1, 2])
def test_non_list_page_fails_closed(which, bad_page, capsys):
    # Mutation pin: dropping the isinstance guard must not pass. A dict page
    # (e.g. an API error object) is not a list of records, on the first page
    # or mid-pagination.
    w, p = World(), pr()
    gh = _gh_world(w, p)
    full = [
        {
            "state": "COMMENTED",
            "commit_id": HEAD,
            "user": {"login": f"zz-{i}"},
            "body": "",
        }
        for i in range(100)
    ]

    def gh2(path):
        if which in path:
            page = int(path.rsplit("page=", 1)[1])
            if page == bad_page:
                return {"message": "not a list"}
            return full if page < bad_page else gh(path)
        return gh(path)

    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=gh2) == 1
    # the exact collect() message: the /files backstop ("changed files
    # incomplete or malformed") must not satisfy this pin.
    assert "list response incomplete or malformed" in capsys.readouterr().out
