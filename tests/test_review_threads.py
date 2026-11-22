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
        "incomplete": 0,
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
    monkeypatch.setattr(rt, "fetch", lambda repo, pr, token: ([thread()], False))
    assert rt.main(["--repo", "o/r", "--pr", "1"]) == 0
    assert rt.main(["--repo", "o/r", "--pr", "1", "--strict"]) == 1


def test_main_writes_the_step_summary(monkeypatch, tmp_path):
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    monkeypatch.setattr(rt, "fetch", lambda repo, pr, token: ([], False))
    assert rt.main(["--repo", "o/r", "--pr", "2"]) == 0
    assert "No review threads." in out.read_text()


# Section: pagination, fail-open and rendering (review 6012414622)


def test_thread_with_more_than_20_comments_is_not_judged_unanswered():
    t = thread(authors=("bot",))
    t["comments"]["pageInfo"] = {"hasNextPage": True}
    assert rt.classify(t)[0] == "incomplete"
    text, counts = rt.summarize([t], 5)
    assert counts["incomplete"] == 1 and counts["unanswered"] == 0
    assert "1 not judged" in text


def test_more_than_100_threads_is_disclosed():
    text, _ = rt.summarize([thread()], 5, more_threads=True)
    assert "Only the first 100 threads were read." in text
    text, _ = rt.summarize([thread()], 5, more_threads=False)
    assert "first 100" not in text


def test_fetch_failure_fails_open_with_an_unavailable_summary(monkeypatch, tmp_path):
    out = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))

    def boom(repo, pr, token):
        raise RuntimeError("secret-looking detail must not be echoed")

    monkeypatch.setattr(rt, "fetch", boom)
    assert rt.main(["--repo", "o/r", "--pr", "1"]) == 0
    text = out.read_text()
    assert "Report unavailable (RuntimeError)" in text
    assert "secret-looking" not in text
    assert rt.main(["--repo", "o/r", "--pr", "1", "--strict"]) == 1


def test_missing_token_and_bad_shape_also_fail_open(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert rt.main(["--repo", "o/r", "--pr", "1"]) == 0
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(rt, "fetch", lambda repo, pr, token: {"unexpected": 1})
    assert rt.main(["--repo", "o/r", "--pr", "1"]) == 0


def test_snippet_drops_markdown_formatting_and_bare_urls():
    snip = rt._snippet(
        "**bold** _it_ ~~x~~ # head > quote \\ ! see https://evil.example/a?b=c now"
    )
    for ch in "*_~#>\\!":
        assert ch not in snip
    assert "https://" not in snip and "evil.example" not in snip
    assert "(link)" in snip
