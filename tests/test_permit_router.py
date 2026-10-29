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


def pr():
    return {"number": 7, "merged": True, "merge_commit_sha": MERGE, "user": {"login": "zz-bot"},
            "head": {"ref": "permit-feed/20261029-0300", "sha": HEAD, "repo": {"full_name": REPO}},
            "base": {"ref": "main", "sha": BASE}}


def prov(run=str(RUN_ID)):
    return {"note": "scan checkpoint binding (issue #566); written by permit_feed.py",
            "checkpoint_commit": CP, "batch": {"offset": 280, "limit": 280}, "source_run": run}


def run():
    return {"id": RUN_ID, "path": ".github/workflows/permit-feed.yml", "repository": {"full_name": REPO},
            "head_repository": {"full_name": REPO}, "head_branch": "main", "event": "schedule",
            "run_attempt": 1, "status": "completed", "conclusion": "success", "head_sha": RUN_HEAD}


def reviews():
    return [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}]


class World:
    def __init__(self):
        self.provenance = {HEAD: prov(), BASE: {**prov("999000"), "checkpoint_commit": "f" * 40}}
        self.run = run()
        self.reviews = reviews()
        self.ancestors = {(MERGE, "main"), (RUN_HEAD, BASE)}
        self.markers = ""
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
        raise AssertionError(kind)


def decide(p=None, w=None):
    w = w or World()
    return pr_mod.decide(REPO, p or pr(), w.read)


def test_verified_scan_pr_routes_to_audit():
    assert decide() == ("route-scan-audit", "verified")


@pytest.mark.parametrize("change,reason", [
    (lambda p: p.update(merged=False), "not merged"),
    (lambda p: p["base"].update(ref="develop"), "not a main data PR"),
    (lambda p: p["head"].update(ref="feature/x"), "not a same-repo permit-feed PR"),
    (lambda p: p["head"].update(repo={"full_name": "zz-fork/zz-repo"}), "not a same-repo permit-feed PR"),
    (lambda p: p["head"].update(repo=None), "fork or deleted head repository"),
])
def test_non_data_or_unmerged_prs_skip_before_any_read(change, reason):
    p, w = pr(), World()
    change(p)
    assert pr_mod.decide(REPO, p, w.read) == ("skip", reason)
    assert w.calls == []


@pytest.mark.parametrize("change", [
    lambda p: p.update(number="7"), lambda p: p.update(head="x"), lambda p: p.update(merge_commit_sha=None),
    lambda p: p["head"].update(sha="A" * 40), lambda p: p["base"].update(sha="b" * 39), None,
])
def test_malformed_pr_stops(change):
    p = pr()
    if change is None:
        p = "not a dict"
    else:
        change(p)
    with pytest.raises(pr_mod.RouterError):
        decide(p)


def test_merge_commit_not_on_main_stops():
    w = World()
    w.ancestors.discard((MERGE, "main"))
    with pytest.raises(pr_mod.RouterError, match="merge commit"):
        decide(w=w)


def test_pr_without_provenance_or_with_inherited_provenance_skips():
    w = World()
    del w.provenance[HEAD]
    assert decide(w=w) == ("skip", "no scan provenance")
    w = World()
    w.provenance[HEAD] = copy.deepcopy(w.provenance[BASE])  # e.g. an enrich PR branched from main
    assert decide(w=w) == ("skip", "provenance not changed by this PR")


@pytest.mark.parametrize("change", [
    lambda d: d.update(source_run=None), lambda d: d.update(source_run=RUN_ID), lambda d: d.update(source_run="0"),
    lambda d: d.update(source_run="1 "), lambda d: d.update(extra=1), lambda d: d.pop("note"),
    lambda d: d.update(checkpoint_commit="x"), lambda d: d.update(batch={"offset": 1}),
    lambda d: d.update(batch={"offset": -1, "limit": 1}), lambda d: d.update(batch={"offset": True, "limit": 1}),
])
def test_forged_or_malformed_provenance_stops(change):
    w = World()
    change(w.provenance[HEAD])
    with pytest.raises(pr_mod.RouterError):
        decide(w=w)


@pytest.mark.parametrize("key,value", [
    ("id", RUN_ID + 1), ("path", ".github/workflows/other.yml"), ("path", ".github/workflows/permit-feed.yml "),
    ("repository", {"full_name": "zz-other/zz-repo"}), ("head_repository", {"full_name": "zz-fork/zz-repo"}),
    ("head_branch", "permit-feed/20261029-0300"), ("event", "pull_request"), ("event", "pull_request_target"),
    ("run_attempt", 2), ("status", "in_progress"), ("conclusion", "failure"), ("conclusion", None),
    ("head_sha", "short"),
])
def test_mismatched_source_run_stops(key, value):
    w = World()
    w.run[key] = value
    with pytest.raises(pr_mod.RouterError, match="source run"):
        decide(w=w)


def test_unreadable_run_and_stale_run_stop():
    w = World()
    w.provenance[HEAD]["source_run"] = "999777"
    with pytest.raises(pr_mod.RouterError):
        decide(w=w)
    w = World()
    w.ancestors.discard((RUN_HEAD, BASE))
    with pytest.raises(pr_mod.RouterError, match="behind the PR base"):
        decide(w=w)


@pytest.mark.parametrize("revs", [
    [], [{"state": "APPROVED", "commit_id": "9" * 40, "user": {"login": "zz-reviewer"}}],
    [{"state": "COMMENTED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}],
    [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "zz-bot"}}],
])
def test_missing_stale_or_self_approval_holds(revs):
    w = World()
    w.reviews = revs
    assert decide(w=w) == ("hold", "no approval at the exact head")


def test_duplicate_delivery_is_skipped_by_exact_marker_only():
    w = World()
    w.markers = "x\n" + pr_mod.marker(7, HEAD, RUN_ID)
    assert decide(w=w) == ("skip", "already routed")
    for other in (pr_mod.marker(8, HEAD, RUN_ID), pr_mod.marker(7, "9" * 40, RUN_ID), pr_mod.marker(7, HEAD, 1)):
        w = World()
        w.markers = other
        assert decide(w=w) == ("route-scan-audit", "verified")


def _gh_world(w, p):
    def gh(path):
        if path == f"repos/{REPO}/pulls/7":
            return p
        if path.startswith(f"repos/{REPO}/compare/"):
            a, b = path.rsplit("/", 1)[1].split("...")
            return {"status": "ahead" if (a, b) in w.ancestors else "diverged"}
        if path.startswith(f"repos/{REPO}/contents/data/permit_scan_provenance.json?ref="):
            rec = w.provenance.get(path.rsplit("=", 1)[1])
            return None if rec is None else {"encoding": "base64",
                                             "content": base64.b64encode(json.dumps(rec).encode()).decode()}
        if path == f"repos/{REPO}/actions/runs/{RUN_ID}":
            return w.run
        if path == f"repos/{REPO}/pulls/7/reviews?per_page=100":
            return w.reviews
        if path == f"repos/{REPO}/issues/7/comments?per_page=100":
            return [{"body": w.markers}]
        return None
    return gh


def test_main_reads_only_fixed_paths_and_prints_value_free_verdict(capsys, tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    w, p = World(), pr()
    seen = []
    gh = _gh_world(w, p)
    assert pr_mod.main(["--repo", REPO, "--pr", "7"], gh=lambda path: (seen.append(path), gh(path))[1]) == 0
    assert capsys.readouterr().out.strip() == "verdict=route-scan-audit reason=verified pr=7 dispatch=off"
    assert out.read_text() == "verdict=route-scan-audit\n"
    assert all(path.startswith(f"repos/{REPO}/") for path in seen)
    assert not any("dispatches" in path or "workflows/" in path for path in seen)


def test_main_stops_red_on_unreadable_records(capsys):
    w, p = World(), pr()
    gh = _gh_world(w, p)
    assert pr_mod.main(["--repo", REPO, "--pr", "7"],
                       gh=lambda path: None if "/reviews" in path else gh(path)) == 1
    assert capsys.readouterr().out.startswith("verdict=stop reason=GitHub record unreadable")
    assert pr_mod.main(["--repo", REPO, "--pr", "8"], gh=gh) == 1


def _workflow():
    import yaml
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/permit-feed-router.yml").read_text()
    return text, yaml.safe_load(text)


def test_router_workflow_is_read_only_dry_run_and_never_runs_pr_code():
    text, wf = _workflow()
    on = wf[True] if True in wf else wf["on"]  # PyYAML reads the `on:` key as True
    assert on == {"pull_request_target": {"types": ["closed"], "branches": ["main"]}}
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"] == {"group": "permit-feed-router-${{ github.event.pull_request.number }}",
                                 "cancel-in-progress": False}
    job = wf["jobs"]["route"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "read", "actions": "read"}
    assert "github.event.pull_request.merged == true" in job["if"]
    checkout, step = job["steps"]
    assert checkout["with"] == {"ref": "${{ github.sha }}", "persist-credentials": False}
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}", "PR_NUMBER": "${{ github.event.pull_request.number }}"}
    assert step["run"].startswith("set -euo pipefail\n")
    assert "permit_router.py" in step["run"]
    for forbidden in ("head.sha", "head.ref }}", "pull_request.body", "pull_request.title", "secrets.",
                      "workflow run", "workflow_dispatch", "dispatches", "write"):
        body = text.split("\non:", 1)[1]
        assert forbidden not in body.replace("startsWith(github.event.pull_request.head.ref", ""), forbidden


@pytest.mark.parametrize("revs,verdict", [
    (reviews() + [{"state": "CHANGES_REQUESTED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}], "hold"),
    (reviews() + [{"state": "DISMISSED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}], "hold"),
    (reviews() + [{"state": "CHANGES_REQUESTED", "commit_id": HEAD, "user": {"login": "zz-other"}}], "hold"),
    (reviews() + [{"state": "COMMENTED", "commit_id": HEAD, "user": {"login": "zz-reviewer"}}], "route-scan-audit"),
    ([{"state": "CHANGES_REQUESTED", "commit_id": BASE, "user": {"login": "zz-reviewer"}}] + reviews(), "route-scan-audit"),
    (reviews() + [{"state": "CHANGES_REQUESTED", "commit_id": HEAD, "user": {"login": "zz-bot"}}], "route-scan-audit"),
])
def test_only_the_latest_decisive_review_per_reviewer_counts(revs, verdict):
    w = World()
    w.reviews = revs
    assert decide(w=w)[0] == verdict


@pytest.mark.parametrize("which", ["/reviews", "/comments"])
def test_full_page_of_reviews_or_comments_stops_instead_of_truncating(which, capsys):
    w, p = World(), pr()
    gh = _gh_world(w, p)
    full = [{"state": "COMMENTED", "commit_id": HEAD, "user": {"login": f"zz-{i}"}, "body": ""} for i in range(100)]
    assert pr_mod.main(["--repo", REPO, "--pr", "7"],
                       gh=lambda path: full if which in path else gh(path)) == 1
    assert "incomplete" in capsys.readouterr().out
