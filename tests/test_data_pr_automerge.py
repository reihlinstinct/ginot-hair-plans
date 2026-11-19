"""Guard tests for the data-PR auto-merge mechanism (issue #1037).

The auto-merge workflow ships disabled (DATA_AUTOMERGE_ENABLED kill
switch) and may only ever touch data-only PRs. These tests pin the guard's
allowlist, JSON sanity, secrets/PII scan and the workflow's kill-switch
gate so a future edit cannot silently widen what merges itself.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "ci"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import data_pr_automerge
from data_pr_automerge import (
    PRODUCER_PREFIXES,
    added_line_clean,
    file_text_at_ref,
    il_id_valid,
    json_sane,
    path_allowed,
)

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "data-automerge.yml"
SCRIPT = Path(__file__).parent.parent / "scripts" / "ci" / "data_pr_automerge.py"

BASE_FILES = {
    "data/permit_requests.json",
    "data/publications_active.json",
    "docs/index.json",
}


# Section: path allowlist


@pytest.mark.parametrize(
    "filename",
    [
        "data/permit_requests.json",
        "docs/index.json",
        "docs/index.html",
        "docs/data.json",
        "docs/permits.html",
        "docs/permits-default.html",
        "docs/permit-ids.json",
        "docs/permit-points.json",
        "docs/publications_active.json",
        "docs/en/index.html",
        "docs/ar/permits.html",
        "docs/ru/permits-default.html",
        "docs/am/index.html",
        "docs/fr/permits.html",
    ],
)
def test_allowlist_accepts_producer_paths(filename):
    assert path_allowed(filename, "modified", BASE_FILES) is None


def test_allowlist_accepts_new_badge_files():
    assert path_allowed("docs/badge/parcel-30038-30.json", "added", BASE_FILES) is None


@pytest.mark.parametrize(
    "filename",
    [
        "src/ginot/i18n/__init__.py",
        "scripts/ci/data_pr_automerge.py",
        ".github/workflows/data-automerge.yml",
        "tests/test_data_pr_automerge.py",
        "docs/about.html",
        "docs/design/anything.md",
        "docs/TRIAGE.md",
        "docs/filter-links.js",
        "data/council_ginot_hair.geojson",
        "requirements.txt",
    ],
)
def test_allowlist_rejects_non_data_paths(filename):
    assert path_allowed(filename, "modified", BASE_FILES) is not None


def test_allowlist_rejects_new_data_files():
    assert path_allowed("data/brand_new.json", "added", BASE_FILES) is not None


@pytest.mark.parametrize("status", ["removed", "renamed"])
def test_allowlist_rejects_deletions_and_renames(status):
    assert path_allowed("data/permit_requests.json", status, BASE_FILES) is not None


def test_allowlist_rejects_modified_badge_path_outside_pattern():
    assert path_allowed("docs/badge/evil.json", "added", BASE_FILES) is not None


# Section: JSON sanity


def test_json_sane_accepts_list_growth_within_bounds():
    base = json.dumps([1, 2, 3, 4])
    head = json.dumps([1, 2, 3, 4, 5, 6])
    assert json_sane("data/x.json", base, head) is None


def test_json_sane_rejects_mass_shrink():
    base = json.dumps(list(range(100)))
    head = json.dumps(list(range(10)))
    assert json_sane("data/x.json", base, head) is not None


def test_json_sane_rejects_key_set_change():
    base = json.dumps({"a": 1, "b": 2})
    head = json.dumps({"a": 1, "c": 3})
    assert json_sane("data/x.json", base, head) is not None


def test_json_sane_rejects_type_change_and_garbage():
    assert json_sane("data/x.json", "[1]", '{"a": 1}') is not None
    assert json_sane("data/x.json", "[1]", "not json") is not None


def test_json_sane_rejects_list_grown_from_empty():
    assert json_sane("data/x.json", "[]", "[1]") is not None


# Section: secrets/PII scan


@pytest.mark.parametrize(
    "line",
    [
        '"token": "ghp_' + "a" * 30 + '",',
        '"pat": "github_pat_' + "A1_" * 10 + '",',
        '"key": "sk-' + "b" * 25 + '",',
        '"secret": "-----BEGIN PRIVATE KEY-----",',
        '"password": "hunter2",',
        '"contact": "clerk@example.gov.il",',
        '"phone": "050-1234567",',
        '"owner_id": "000000018",',
    ],
)
def test_added_line_clean_flags_secrets_and_pii(line):
    assert added_line_clean(line) is not None


def test_added_line_clean_passes_public_permit_data():
    line = '"tik": "1983/0461.03", "status": "פורסם", "gush": 30038, "helka": 30'
    assert added_line_clean(line) is None


def test_il_id_valid_checksum():
    assert il_id_valid("000000018")
    assert not il_id_valid("000000019")


# Section: workflow and script contract


def test_workflow_ships_disabled_behind_kill_switch():
    text = WORKFLOW.read_text()
    assert "vars.DATA_AUTOMERGE_ENABLED == 'true'" in text


def test_workflow_is_scheduled_and_dispatchable_with_timeout():
    text = WORKFLOW.read_text()
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "timeout-minutes:" in text


def test_merge_is_bound_to_validated_head_sha():
    workflow = WORKFLOW.read_text()
    assert 'sha="$MERGE_SHA"' in workflow
    assert "merge_method=squash" in workflow
    script = SCRIPT.read_text()
    assert "--admin" not in script
    # The merge call lives only in the gated workflow step, never in the
    # script itself (test_no_review_bypass.py enforces this repo-wide).
    assert "pulls/{number}/merge" not in script
    assert "mergePullRequest" not in script


def test_merge_step_is_gated_on_the_kill_switch():
    workflow = WORKFLOW.read_text()
    merge_step = workflow.split("Squash-merge the validated PR", 1)[1]
    assert "vars.DATA_AUTOMERGE_ENABLED == 'true'" in merge_step.split("run:", 1)[0]


def test_guard_defaults_to_one_merge_per_run():
    text = SCRIPT.read_text()
    assert "default=1" in text
    assert "GITHUB_OUTPUT" in text


def test_guard_runs_from_default_branch_checkout():
    """The workflow must not checkout the PR head: the guard version on the
    default branch is the one a data PR cannot modify."""
    text = WORKFLOW.read_text()
    assert "ref:" not in text.split("steps:", 1)[1].split("run:", 1)[0]


# Section: producer prefixes


def test_producer_prefixes_cover_all_scanner_producers():
    """Owner policy 19.11.2026: scanner data-refresh PRs auto-merge on green
    checks without review. The mavat-check producer must be included."""
    for prefix in (
        "permit-feed/",
        "weekly-refresh/",
        "mirror-ingest/",
        "publications/",
        "mavat-check/",
    ):
        assert prefix in PRODUCER_PREFIXES


# Section: large-file blob fallback


def _b64(text: str) -> str:
    import base64

    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_file_text_uses_contents_payload_when_present(monkeypatch):
    calls = []

    def fake_gh_api(path):
        calls.append(path)
        return {"content": _b64('{"a": 1}')}

    monkeypatch.setattr(data_pr_automerge, "gh_api", fake_gh_api)
    assert file_text_at_ref("o/r", "data/x.json", "main") == '{"a": 1}'
    assert len(calls) == 1 and "contents" in calls[0]


def test_file_text_falls_back_to_blob_api_over_1mb(monkeypatch):
    """The contents API omits content for files over 1MB; the guard must
    fetch the same bytes through the git blob API instead of failing the
    JSON sanity check (permit_mirror.json regression, PR #1058)."""
    calls = []

    def fake_gh_api(path):
        calls.append(path)
        if "contents" in path:
            return {"content": "", "sha": "deadbeef", "encoding": "none"}
        return {"content": _b64('{"big": true}')}

    monkeypatch.setattr(data_pr_automerge, "gh_api", fake_gh_api)
    assert file_text_at_ref("o/r", "data/x.json", "main") == '{"big": true}'
    assert any("git/blobs/deadbeef" in c for c in calls)


def test_file_text_fails_closed_without_content_or_sha(monkeypatch):
    monkeypatch.setattr(data_pr_automerge, "gh_api", lambda path: {})
    with pytest.raises(RuntimeError):
        file_text_at_ref("o/r", "data/x.json", "main")


def test_file_text_fails_closed_on_empty_blob(monkeypatch):
    def fake_gh_api(path):
        if "contents" in path:
            return {"content": "", "sha": "deadbeef", "encoding": "none"}
        return {"content": ""}

    monkeypatch.setattr(data_pr_automerge, "gh_api", fake_gh_api)
    with pytest.raises(RuntimeError):
        file_text_at_ref("o/r", "data/x.json", "main")


# Section: immediate trigger on check completion


def _pr_triggered_workflow_names():
    import yaml

    names = set()
    for wf in WORKFLOW.parent.glob("*.yml"):
        if wf.name == WORKFLOW.name:
            continue
        loaded = yaml.safe_load(wf.read_text())
        on = loaded.get("on", loaded.get(True))  # YAML 1.1 "on" -> True
        if isinstance(on, str):
            on = {on: None}
        if isinstance(on, list):
            on = {k: None for k in on}
        if on and "pull_request" in on:
            names.add(loaded.get("name", wf.stem))
    return names


def test_workflow_run_trigger_re_evaluates_on_check_completion():
    """Owner request 19.11.2026 (phonemsg-01M7T38FF8K2G7RF6YERYCK5EG):
    producers trigger the automerge right after their PR opens. The
    mechanism is workflow_run on check workflows completing on producer
    branches - it runs this workflow from the default branch, so the
    guard a PR cannot change is always the one evaluating it. No
    pull_request_target: that trigger would hand PR-controlled context
    to a secrets-bearing workflow."""
    import yaml

    loaded = yaml.safe_load(WORKFLOW.read_text())
    on = loaded.get("on", loaded.get(True))  # YAML 1.1 parses the key "on" as bool
    assert "pull_request_target" not in on
    assert "pull_request" not in on
    trigger = on["workflow_run"]
    assert trigger["types"] == ["completed"]
    # Every pull_request-triggered workflow must be in the list so a
    # rename cannot silently drop the immediate path.
    missing = _pr_triggered_workflow_names() - set(trigger["workflows"])
    assert not missing, f"pull_request workflows missing from workflow_run: {missing}"
    branches = trigger["branches"]
    for prefix in (
        "permit-feed/",
        "weekly-refresh/",
        "mirror-ingest/",
        "publications/",
        "mavat-check/",
    ):
        assert f"{prefix}**" in branches


# Section: sweep robustness


def _two_producer_prs():
    return [
        {
            "number": 1,
            "title": "Weekly refresh",
            "head": {
                "repo": {"full_name": "o/r"},
                "ref": "weekly-refresh/1",
                "sha": "a" * 40,
            },
            "user": {"login": "o"},
        },
        {
            "number": 2,
            "title": "Mirror ingest",
            "head": {
                "repo": {"full_name": "o/r"},
                "ref": "mirror-ingest/2",
                "sha": "b" * 40,
            },
            "user": {"login": "o"},
        },
    ]


def _patch_sweep(monkeypatch, check):
    monkeypatch.setattr(
        data_pr_automerge, "gh_api_paginated", lambda path: _two_producer_prs()
    )
    monkeypatch.setattr(
        data_pr_automerge,
        "gh_api",
        lambda path, method="GET", payload=None: {"tree": []},
    )
    monkeypatch.setattr(data_pr_automerge, "check_pr", check)
    monkeypatch.setenv("GH_TOKEN", "test")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["data_pr_automerge.py", "--repo", "o/r", "--dry-run"]
    )


def test_malformed_blob_decode_skips_one_pr_not_the_sweep(monkeypatch, capsys):
    """base64/UTF-8 decode failures are ValueErrors: one malformed file
    skips its PR instead of aborting the whole sweep (review follow-up, #1061)."""

    def check(repo, pr, base_files):
        if pr["number"] == 1:
            raise ValueError("malformed blob")
        return []

    _patch_sweep(monkeypatch, check)
    assert data_pr_automerge.main() == 0
    out = capsys.readouterr().out
    assert "PR #1: SKIP - guard error: malformed blob" in out
    assert "PR #2: eligible (dry run, not merged)" in out


def test_unexpected_error_aborts_the_sweep_fail_closed(monkeypatch):
    """TimeoutExpired/TypeError are not data-decode errors: the sweep aborts
    rather than guessing (fail closed)."""

    def check(repo, pr, base_files):
        raise TypeError("unexpected")

    _patch_sweep(monkeypatch, check)
    with pytest.raises(TypeError):
        data_pr_automerge.main()
