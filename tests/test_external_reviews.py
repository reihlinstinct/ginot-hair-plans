import json
import subprocess
import sys
from pathlib import Path

import pytest

from ginot import external_reviews as er
from ginot import page

ROOT = Path(__file__).resolve().parents[1]
OK = {"id": "x1", "pl_number": "101-1", "agent_name": "Test Bot", "text": "t" * 60,
      "submitted": "2026-10-22", "approved": "2026-10-23"}


def test_live_file_is_valid():
    assert er.validate_entries(er.load(ROOT / "data/external_reviews.json")) == []


def test_validation_rejects_bad_entries():
    assert er.validate_entries([OK]) == []
    assert er.validate_entries([OK, dict(OK)])  # duplicate id
    for bad in ({"text": "see https://x.example " + "t" * 40}, {"text": "<b>" + "t" * 60},
                {"text": "short"}, {"agent_name": "bad<name>"}, {"approved": "yesterday"}):
        assert er.validate_entries([{**OK, **bad}]), bad
    assert er.validate_entries([{k: v for k, v in OK.items() if k != "id"}])


def test_regression_append_only_rejects_edit_removal_reorder():
    a, b = OK, {**OK, "id": "x2", "text": "u" * 60}
    assert er.check_append_only([a], [a, b]) == []
    assert er.check_append_only([a, b], [a])  # removal
    assert er.check_append_only([a], [{**a, "text": "z" * 60}])  # edit
    assert er.check_append_only([a, b], [b, a])  # reorder
    assert er.check_append_only([], [a]) == []


def test_ci_guard_script_fails_on_modified_entry(tmp_path):
    base = {"entries": [OK]}
    repo = tmp_path
    (repo / "data").mkdir()
    run = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (repo / "data/external_reviews.json").write_text(json.dumps(base))
    run("git", "add", ".")
    run("git", "commit", "-qm", "base")
    script = ROOT / "scripts/ci/check_external_reviews.py"
    (repo / "data/external_reviews.json").write_text(json.dumps({"entries": [{**OK, "text": "e" * 60}]}))
    r = subprocess.run([sys.executable, str(script), "--base", "main"], cwd=repo, capture_output=True, text=True, check=False,
                       env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 1 and "modified" in r.stdout
    (repo / "data/external_reviews.json").write_text(json.dumps({"entries": [OK, {**OK, "id": "x2"}]}))
    r = subprocess.run([sys.executable, str(script), "--base", "main"], cwd=repo, capture_output=True, text=True, check=False,
                       env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stdout


def test_section_is_labelled_collapsed_and_escaped():
    html = er.render_section([{**OK, "text": "a&b " + "t" * 60}], "101-1")
    assert "<details" in html and "open" not in html.split(">")[0]
    assert "לא מאומתות" in html and "a&amp;b" in html
    assert er.render_section([OK], "other") == ""


@pytest.mark.parametrize("entries,shown", [([OK], True), ([], False)])
def test_review_page_shows_section_after_our_review(entries, shown):
    out = page.render_review("101-1", "# our review", "2026-10-22", "c", external_html=er.render_section(entries, "101-1"))
    assert ("external-reviews" in out) is shown
    if shown:
        assert out.index("our review") < out.index("external-reviews")
