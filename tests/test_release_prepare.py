import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "prepare", Path(__file__).parent.parent / "scripts/releases/prepare.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_label_driven_semantic_bumps():
    assert release.bump("0.2.0", [{"labels": [{"name": "bug"}]}]) == "0.2.1"
    assert release.bump("0.2.5", [{"labels": [{"name": "enhancement"}]}]) == "0.3.0"
    assert release.bump("0.2.5", [{"labels": [{"name": "breaking"}]}]) == "1.0.0"


def test_preparation_updates_version_notes_changelog_and_footer(tmp_path):
    (tmp_path / "src/ginot").mkdir(parents=True)
    (tmp_path / "src/ginot/__init__.py").write_text('__version__ = "0.2.0"')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/index.html").write_text(
        '<p>גרסה <span dir="ltr">0.2.0</span> · Version 0.2.0</p>'
    )
    version = release.prepare(
        tmp_path,
        [
            {
                "number": 1,
                "title": "Fix example",
                "mergedAt": "2026-10-22",
                "labels": [{"name": "bug"}],
            }
        ],
        "2026-10-22",
    )
    assert version == "0.2.1"
    notes = (tmp_path / "releases/0.2.1.md").read_text()
    assert "## עברית" in notes and "## English" in notes and "#1" in notes
    assert "0.2.1" in (tmp_path / "CHANGELOG.md").read_text()
    assert "0.2.0" not in (tmp_path / "docs/index.html").read_text()


def test_prepare_rejects_empty_pr_list(tmp_path):
    (tmp_path / "src/ginot").mkdir(parents=True)
    (tmp_path / "src/ginot/__init__.py").write_text('__version__ = "0.2.0"')
    import pytest

    with pytest.raises(ValueError, match="no merged PRs"):
        release.prepare(tmp_path, [{"number": 1, "title": "x", "labels": []}], "2026-10-25")


def test_main_with_prs_file(tmp_path, capsys, monkeypatch):
    import json as _json

    (tmp_path / "src/ginot").mkdir(parents=True)
    (tmp_path / "src/ginot/__init__.py").write_text('__version__ = "0.2.0"')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    (tmp_path / "docs").mkdir()
    prs = tmp_path / "prs.json"
    prs.write_text(_json.dumps([
        {"number": 7, "title": "Add thing", "mergedAt": "2026-10-24",
         "labels": [{"name": "feature"}], "url": "u"}
    ]))
    monkeypatch.setattr(
        "sys.argv",
        ["prepare.py", "--prs", str(prs), "--date", "2026-10-25", "--root", str(tmp_path)],
    )
    release.main()
    assert capsys.readouterr().out.strip() == "0.3.0"


def test_main_collects_prs_via_git_and_gh(tmp_path, monkeypatch):
    import json as _json

    (tmp_path / "src/ginot").mkdir(parents=True)
    (tmp_path / "src/ginot/__init__.py").write_text('__version__ = "0.2.0"')
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n")
    (tmp_path / "docs").mkdir()
    calls = []

    class _R:
        returncode = 0
        stdout = "v0.2.0\n"

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _R()

    def fake_check_output(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["git", "show"]:
            return "2026-10-20T00:00:00+00:00\n"
        return _json.dumps([
            {"number": 9, "title": "T", "mergedAt": "2026-10-24", "labels": []}
        ])

    monkeypatch.setattr(release.subprocess, "run", fake_run)
    monkeypatch.setattr(release.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        "sys.argv",
        ["prepare.py", "--date", "2026-10-25", "--root", str(tmp_path)],
    )
    release.main()
    gh = next(c for c in calls if c[0] == "gh")
    assert "merged:>2026-10-20T00:00:00+00:00" in gh
    assert '0.2.1' in (tmp_path / "src/ginot/__init__.py").read_text()
