"""Tests for the private-names guard (issue #1053)."""

import hashlib
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "private_names_guard", ROOT / "scripts" / "ci" / "private_names_guard.py"
)
png = importlib.util.module_from_spec(spec)
spec.loader.exec_module(png)


def _h(text: str) -> str:
    return hashlib.sha256(text.lower().encode()).hexdigest()[:16]


# Section: token and phrase detection


def test_blocked_single_token_detected():
    hashes = frozenset({_h("secret-example")})
    hits = png.find_hits("nothing here\nsecret-example appeared\n", hashes)
    assert hits == [(2, _h("secret-example"))]


def test_blocked_two_token_phrase_detected():
    hashes = frozenset({_h("alpha 1497")})
    hits = png.find_hits("usage was alpha 1497 minutes\n", hashes)
    assert hits == [(1, _h("alpha 1497"))]


def test_matching_is_case_insensitive():
    hashes = frozenset({_h("secret-example")})
    assert png.find_hits("Secret-Example\n", hashes)


def test_clean_text_has_no_hits():
    hashes = frozenset({_h("secret-example"), _h("alpha 1497")})
    assert png.find_hits("ordinary public text\nwith words 1497 alone\n", hashes) == []


def test_hyphenated_name_is_one_token():
    hashes = frozenset({_h("acme-reports")})
    assert png.find_hits("see acme-reports here\n", hashes)


def test_hits_report_hash_not_plaintext():
    hits = png.find_hits("oops secret-example\n", frozenset({_h("secret-example")}))
    assert hits and "secret-example" not in hits[0][1]


# Section: blocklist loading


def test_repo_blocklist_loads():
    assert len(png.load_hashes()) > 0


def test_load_hashes_from_path(tmp_path):
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps({"hashes": [_h("x")]}), encoding="utf-8")
    assert png.load_hashes(path) == frozenset({_h("x")})


# Section: CLI behavior


def test_cli_clean_text_exits_zero(capsys):
    assert png.main(["--text", "all clean here"]) == 0
    assert "clean" in capsys.readouterr().out


def test_cli_scans_given_file(tmp_path, capsys):
    target = tmp_path / "note.txt"
    target.write_text("ordinary words only\n", encoding="utf-8")
    assert png.main(["--file", str(target)]) == 0


# Section: tracked-content regression


def test_tracked_content_has_no_blocked_entries():
    hashes = png.load_hashes()
    problems = png.scan_paths(png.tracked_files(), hashes)
    assert problems == []
