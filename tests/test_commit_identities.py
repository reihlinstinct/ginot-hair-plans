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
