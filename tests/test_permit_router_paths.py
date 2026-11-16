"""Post-merge permit router decisions (#565). Synthetic records only."""

import copy
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


# Section: Paths


@pytest.mark.parametrize(
    "path",
    [
        "scripts/ci/permit_router.py",
        ".github/workflows/permit-feed-router.yml",
        ".github/workflows/permit-feed.yml",
        "src/zz.py",
        "tests/test_permit_router.py",
        "docs/other.html",
        "docs/badge/parcel-1/x.json",
        "docs/badge/other.json",
        "data/../scripts/x.py",
        "data//x.json",
        "/data/x.json",
        "data\\x.json",
        "",
        None,
    ],
)
def test_pr_touching_anything_but_generated_data_stops(path):
    w = World()
    w.files = files(DATA_FILES[:-1]) + [{"filename": path, "status": "modified"}]
    with pytest.raises(
        pr_mod.RouterError, match="changed files|outside the generated data"
    ):
        decide(w=w)


def test_rename_from_code_into_data_stops():
    w = World()
    w.files = files(DATA_FILES[:-1]) + [
        {
            "filename": "data/x.py",
            "status": "renamed",
            "previous_filename": "scripts/ci/permit_router.py",
        }
    ]
    with pytest.raises(pr_mod.RouterError, match="outside the generated data"):
        decide(w=w)


@pytest.mark.parametrize(
    "listing",
    [
        [],
        None,
        "x",
        files(DATA_FILES[:-1]),
        files() + files(["data/y.json"]),
        files(DATA_FILES[:-1]) + ["data/x.json"],
    ],
)
def test_incomplete_or_malformed_changed_file_list_stops(listing):
    w = World()
    w.files = listing
    with pytest.raises(pr_mod.RouterError, match="changed files"):
        decide(w=w)


def test_every_staged_data_path_is_allowed():
    staged = [
        "data/a/b.json",
        "docs/index.json",
        "docs/badge/parcel-12-3.json",
        "docs/permits.html",
        "docs/permits-default.html",
        "docs/permit-ids.json",
        "docs/permit-points.json",
    ]
    w, p = World(), pr()
    w.files = files(staged)
    p["changed_files"] = len(staged)
    assert pr_mod.decide(REPO, p, w.read) == ("route-scan-audit", "verified")


def test_changed_files_are_checked_before_provenance_is_trusted():
    w = World()
    w.files = files(DATA_FILES[:-1] + ["scripts/ci/permit_router.py"])
    with pytest.raises(pr_mod.RouterError):
        decide(w=w)
    assert not any(
        call[0] in ("provenance", "run", "reviews", "markers") for call in w.calls
    )


def test_generated_index_html_remains_routable_with_full_checks():
    # #870: the permit renderer updates coverage counts in this exact file.
    p, w = pr(), World()
    w.files.append({"filename": "docs/index.html", "status": "modified"})
    p["changed_files"] += 1
    assert decide(p, w) == ("route-scan-audit", "verified")
    w.reviews = []
    assert decide(p, w)[0] == "hold"


@pytest.mark.parametrize(
    "path",
    [
        "docs/arbitrary.html",
        "docs/reviews/private.html",
        "scripts/index.html",
        ".github/workflows/index.html",
    ],
)
def test_index_html_allowance_does_not_allow_other_html(path):
    p, w = pr(), World()
    w.files.append({"filename": path, "status": "modified"})
    p["changed_files"] += 1
    with pytest.raises(pr_mod.RouterError, match="outside the generated data"):
        decide(p, w)


# Section: per-language permit fragments (#942 follow-up; Tab review on #970)


def _non_default_langs():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from ginot import i18n

    return [c for c in i18n.lang_codes() if c != i18n.default_lang()]


def test_every_language_permit_fragment_is_allowed():
    langs = _non_default_langs()
    assert langs, "expected at least one non-default language in the document"
    staged = DATA_FILES[:-1] + [
        f"docs/{code}/{name}"
        for code in langs
        for name in ("permits.html", "permits-default.html")
    ]
    p, w = pr(), World()
    w.files = files(staged)
    p["changed_files"] = len(staged)
    assert decide(p, w) == ("route-scan-audit", "verified")


@pytest.mark.parametrize(
    "path",
    [
        "docs/he/permits.html",  # default language lives at the root
        "docs/he/permits-default.html",
        "docs/reviews/permits.html",
        "docs/vendor/permits.html",
        "docs/badge/permits-default.html",
        "docs/.well-known/permits.html",
        "docs/zz/permits.html",
        "docs/FR/permits.html",  # codes are case-sensitive
        "docs/en/a/permits.html",  # nested
        "docs/en/permit.html",  # wrong filename
        "docs/en/permits.htmlx",
        "docs/en/permits-default.htm",
    ],
)
def test_non_language_permit_fragment_paths_stop(path):
    p, w = pr(), World()
    w.files.append({"filename": path, "status": "modified"})
    p["changed_files"] += 1
    with pytest.raises(pr_mod.RouterError, match="outside the generated data"):
        decide(p, w)


def test_rename_from_code_into_language_fragment_stops():
    p, w = pr(), World()
    w.files.append(
        {
            "filename": "docs/en/permits.html",
            "status": "renamed",
            "previous_filename": "scripts/ci/permit_router.py",
        }
    )
    p["changed_files"] += 1
    with pytest.raises(pr_mod.RouterError, match="outside the generated data"):
        decide(p, w)
