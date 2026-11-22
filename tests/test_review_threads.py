"""Unit tests for scripts/ci/review_threads.py (#454): thread states, bot
counting, the plain-text snippet rule, and that the informational run never
fails unless --strict is given."""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "review_threads", ROOT / "scripts/ci/review_threads.py"
)
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


# Section: builders


def thread(resolved=False, outdated=False, authors=("bot",), bot=True, body="x"):
    nodes = []
    for i, login in enumerate(authors):
        typename = "Bot" if (bot and i == 0) else "User"
        nodes.append({"author": {"login": login, "__typename": typename}, "body": body})
    return {
        "isResolved": resolved,
        "isOutdated": outdated,
        "path": "a/b.py",
        "comments": {"nodes": nodes},
    }


# Section: classification


def test_states_resolved_answered_unanswered():
    assert rt.classify(thread(resolved=True))[0] == "resolved"
    assert rt.classify(thread(authors=("bot", "owner")))[0] == "answered"
    assert rt.classify(thread(authors=("bot",)))[0] == "unanswered"


def test_a_reply_by_the_starter_does_not_count_as_an_answer():
    assert rt.classify(thread(authors=("bot", "bot")))[0] == "unanswered"


def test_missing_author_is_unknown_not_a_crash():
    t = {"isResolved": False, "comments": {"nodes": [{"author": None, "body": ""}]}}
    assert rt.classify(t) == ("unanswered", "unknown", False)


# Section: summary text


def test_summary_counts_and_flags_bot_unanswered():
    text, counts = rt.summarize(
        [thread(), thread(resolved=True), thread(authors=("u", "o"), bot=False)], 7
    )
    assert counts == {
        "resolved": 1,
        "answered": 1,
        "unanswered": 1,
        "bot_unanswered": 1,
    }
    assert "#7" in text and "1 from a bot" in text


def test_empty_threads_say_so():
    text, counts = rt.summarize([], 3)
    assert "No review threads." in text and counts["unanswered"] == 0


def test_snippet_is_plain_truncated_and_drops_markup():
    body = "<!-- hidden -->**Bold** | pipe `code` <b>tag</b> " + "z" * 300
    snip = rt._snippet(body)
    assert len(snip) <= rt.SNIPPET_CHARS
    assert "<" not in snip and "|" not in snip and "`" not in snip
    assert "hidden" not in snip


def test_table_cell_cannot_break_the_row_with_a_pipe_or_newline():
    text, _ = rt.summarize([thread(body="a | b\nc")], 1)
    row = next(ln for ln in text.splitlines() if ln.startswith("| unanswered"))
    assert row.count("|") == 6 and "\n" not in row


# Section: exit codes


def test_main_is_informational_unless_strict(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(rt, "fetch", lambda repo, pr, token: [thread()])
    assert rt.main(["--repo", "o/r", "--pr", "1"]) == 0
    assert rt.main(["--repo", "o/r", "--pr", "1", "--strict"]) == 1


def test_main_writes_the_step_summary(monkeypatch, tmp_path):
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    monkeypatch.setattr(rt, "fetch", lambda repo, pr, token: [])
    assert rt.main(["--repo", "o/r", "--pr", "2"]) == 0
    assert "No review threads." in out.read_text()
