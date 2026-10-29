"""Scan checkpoint <-> data PR lifecycle binding (issue #566).

Synthetic and offline: a fake GitHub REST router stands in for gh_api, and
call() is replaced, so no municipal or GitHub request is ever made.
"""

import base64
import importlib.util
import json
import pathlib
import sys

import pytest

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location("permit_feed", vpn / "permit_feed.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)
lc = pf.checkpoint_lifecycle

SLUG = "example/repo"
CP = "c" * 40
OTHER = "d" * 40
CP_DATE = "2026-10-29T03:30:00Z"


def _prov(commit=CP, offset=280, limit=280):
    return lc.provenance(commit, offset, limit, "123")


def _pr(number, state="closed", merged=False, prov=None):
    return {"number": number, "state": state, "merged": merged, "provenance": prov}


# --- decide() -------------------------------------------------------------

CP_BATCH = {"offset": 280, "limit": 280, "done": 281}
MAIN_BEFORE = {"offset": 0, "limit": 280}  # cursor before the checkpoint batch


def test_no_checkpoint_proceeds():
    assert lc.decide(None, None, MAIN_BEFORE, [_pr(1, prov=_prov())]) == ("none", [])


def test_unbound_checkpoint_resumes_as_before():
    # Lost runner before publish, or a PR from before #566 (no provenance).
    prs = [_pr(1, prov=None), _pr(2, prov=_prov(commit=OTHER))]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("unbound", [])


def test_closed_unmerged_checkpoint_is_rejected():
    prs = [_pr(7, prov=_prov())]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("rejected", [7])
    assert "rejected" not in lc.PROCEED


def test_merged_checkpoint_is_consumed():
    prs = [_pr(7, prov=_prov()), _pr(8, merged=True, prov=_prov())]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("consumed", [7, 8])


@pytest.mark.parametrize("main_offset", [280, 560])
def test_replaced_or_overtaken_checkpoint_is_stale(main_offset):
    # A re-authored replacement landed this batch (main cursor == checkpoint
    # offset), or main moved past it: the checkpoint cannot be resumed.
    main = {"offset": main_offset, "limit": 280}
    assert lc.decide(CP, CP_BATCH, main, [_pr(7, prov=_prov())]) == ("stale", [7])


def test_missing_main_cursor_counts_as_not_landed():
    assert lc.decide(CP, CP_BATCH, None, [_pr(7, prov=_prov())])[0] == "rejected"


def test_open_bound_pr_is_pending():
    prs = [_pr(7, prov=_prov()), _pr(9, state="open", prov=_prov())]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("pending", [7, 9])


def test_open_bound_pr_blocks_even_beside_a_merged_one():
    prs = [_pr(8, merged=True, prov=_prov()), _pr(9, state="open", prov=_prov())]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("pending", [8, 9])


@pytest.mark.parametrize(
    "prov",
    [
        _prov(offset=560),
        _prov(limit=60),
        {"checkpoint_commit": CP, "batch": {"offset": "280", "limit": 280}},
        {"checkpoint_commit": CP},
    ],
)
def test_bound_pr_with_other_batch_is_mismatch(prov):
    # Even a merged PR cannot vouch for a checkpoint it does not describe.
    prs = [_pr(7, merged=True, prov=prov)]
    assert lc.decide(CP, CP_BATCH, MAIN_BEFORE, prs) == ("mismatch", [7])


def test_checkpoint_without_batch_fails_closed():
    with pytest.raises(lc.LifecycleError):
        lc.decide(CP, {"offset": 1}, MAIN_BEFORE, [])


# --- fake GitHub -------------------------------------------------------------


def _b64(obj):
    return base64.b64encode(json.dumps(obj).encode()).decode()


class FakeGitHub:
    """Routes the REST paths the feed uses; records every call."""

    def __init__(self):
        self.branch = None  # (sha, date) of scan-checkpoint, or None
        self.files = {}  # (path, ref) -> object
        self.prs = []  # raw pull objects, newest update first
        self.calls = []
        self.puts = []

    def pull(
        self,
        number,
        sha,
        *,
        state="closed",
        merged=False,
        repo=SLUG,
        ref=None,
        created="2026-10-29T04:00:00Z",
        updated="2026-10-29T05:00:00Z",
    ):
        self.prs.append(
            {
                "number": number,
                "state": state,
                "merged_at": "2026-10-29T05:00:00Z" if merged else None,
                "created_at": created,
                "updated_at": updated,
                "head": {
                    "ref": ref or f"permit-feed/2026102{number % 10}-0300",
                    "sha": sha,
                    "repo": None if repo is None else {"full_name": repo},
                },
            }
        )

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path))
        base = f"/repos/{SLUG}"
        assert path.startswith(base), path
        rest = path[len(base) :]
        if method == "GET" and rest == "/branches/scan-checkpoint":
            if not self.branch:
                return {"message": "Branch not found"}
            sha, date = self.branch
            return {"commit": {"sha": sha, "commit": {"committer": {"date": date}}}}
        if method == "GET" and rest == "/git/ref/heads/scan-checkpoint":
            return (
                {"object": {"sha": self.branch[0]}}
                if self.branch
                else {"message": "Not Found"}
            )
        if method == "GET" and rest == "/git/ref/heads/main":
            return {"object": {"sha": "m" * 40}}
        if method == "POST" and rest == "/git/refs":
            self.branch = (payload["sha"], CP_DATE)
            return {"ref": payload["ref"]}
        if method == "GET" and rest.startswith("/pulls?"):
            page = int(rest.rsplit("page=", 1)[1])
            return self.prs[(page - 1) * 100 : page * 100]
        if method == "GET" and rest.startswith("/contents/"):
            fpath, ref = rest[len("/contents/") :].split("?ref=")
            if (fpath, ref) not in self.files:
                return {"message": "Not Found"}
            return {"sha": "blob", "content": _b64(self.files[(fpath, ref)])}
        if method == "PUT" and rest == "/contents/data/permit_requests.json":
            new = f"{len(self.puts) + 1:040d}"
            content = json.loads(base64.b64decode(payload["content"]))
            self.puts.append(content)
            self.files[("data/permit_requests.json", "scan-checkpoint")] = content
            self.files[("data/permit_requests.json", new)] = content
            self.branch = (new, CP_DATE)
            return {"commit": {"sha": new}}
        raise AssertionError(f"unexpected GitHub call {method} {path}")


def _checkpoint(gh, sha=CP, offset=280, limit=280, done=281):
    gh.branch = (sha, CP_DATE)
    gh.files[("data/permit_requests.json", sha)] = pf.checkpoint_payload(
        {}, offset, limit, done
    )


def _gate(gh, monkeypatch, main_batch=MAIN_BEFORE):
    monkeypatch.setattr(pf, "gh_api", gh)
    return pf.lifecycle_gate("t", SLUG, main_batch)[:2]


# --- lifecycle_gate() / candidate_prs() ------------------------------------------


def test_gate_reads_provenance_at_exact_pr_head(monkeypatch):
    gh = FakeGitHub()
    _checkpoint(gh)
    gh.pull(7, "a" * 40)
    gh.files[(lc.PROVENANCE_PATH, "a" * 40)] = _prov()
    assert _gate(gh, monkeypatch) == ("rejected", [7])
    assert (
        "GET",
        f"/repos/{SLUG}/contents/{lc.PROVENANCE_PATH}?ref={'a' * 40}",
    ) in gh.calls
    # The checkpoint itself is read at the head SHA the verdict is about.
    assert (
        "GET",
        f"/repos/{SLUG}/contents/data/permit_requests.json?ref={CP}",
    ) in gh.calls


def test_gate_without_checkpoint_branch_is_none(monkeypatch):
    assert _gate(FakeGitHub(), monkeypatch) == ("none", [])


def test_gate_ignores_untrusted_and_older_prs(monkeypatch):
    gh = FakeGitHub()
    _checkpoint(gh)
    for n, kw in [
        (1, {"repo": "someone/fork"}),
        (2, {"repo": None}),  # deleted fork
        (3, {"ref": "weekly-refresh/x"}),
        (4, {"created": "2026-10-29T03:00:00Z"}),  # opened before the checkpoint
    ]:
        gh.pull(n, f"{n}" * 40, **kw)
        gh.files[(lc.PROVENANCE_PATH, f"{n}" * 40)] = _prov()
    gh.pull(5, "5" * 40)  # trusted, but from before #566: no provenance file
    assert _gate(gh, monkeypatch) == ("unbound", [])
    reads = [p for _, p in gh.calls if lc.PROVENANCE_NAME in p]
    assert reads == [f"/repos/{SLUG}/contents/{lc.PROVENANCE_PATH}?ref={'5' * 40}"]


def test_gate_stops_paging_at_prs_older_than_checkpoint(monkeypatch):
    gh = FakeGitHub()
    _checkpoint(gh)
    for n in range(100):
        gh.pull(1000 + n, "e" * 40, ref="other/x", updated="2026-10-28T00:00:00Z")
    assert _gate(gh, monkeypatch) == ("unbound", [])
    assert sum(1 for _, p in gh.calls if "/pulls?" in p) == 1


def test_gate_pages_until_short_page(monkeypatch):
    gh = FakeGitHub()
    _checkpoint(gh)
    for n in range(100):
        gh.pull(1000 + n, "e" * 40, ref="other/x")
    gh.pull(7, "a" * 40)
    gh.files[(lc.PROVENANCE_PATH, "a" * 40)] = _prov()
    assert _gate(gh, monkeypatch) == ("rejected", [7])


@pytest.mark.parametrize(
    "breakage",
    [
        "branch_error",
        "page_error",
        "malformed_pr",
        "provenance_error",
        "provenance_garbage",
        "contents_error",
        "contents_empty",
        "contents_garbage",
        "contents_null",
        "contents_list",
        "too_many_pages",
    ],
)
def test_gate_fails_closed(monkeypatch, breakage):
    gh = FakeGitHub()
    _checkpoint(gh)
    gh.pull(7, "a" * 40)
    gh.files[(lc.PROVENANCE_PATH, "a" * 40)] = _prov()
    real = FakeGitHub.__call__

    def broken(self, method, path, token, payload=None):
        if breakage == "branch_error" and "/branches/" in path:
            return {"message": "API rate limit exceeded"}
        if breakage == "page_error" and "/pulls?" in path:
            return {"message": "Bad credentials"}
        if breakage == "malformed_pr" and "/pulls?" in path:
            return [{"number": 7}]
        if breakage == "provenance_error" and lc.PROVENANCE_NAME in path:
            return {"message": "Server Error"}
        if breakage == "provenance_garbage" and lc.PROVENANCE_NAME in path:
            return {"content": base64.b64encode(b"not json").decode()}
        checkpoint_read = "/contents/data/permit_requests.json" in path
        if breakage == "contents_error" and checkpoint_read:
            return {"message": "API rate limit exceeded"}
        if breakage == "contents_empty" and checkpoint_read:
            return {"sha": "blob", "content": "", "encoding": "none"}
        if breakage == "contents_garbage" and checkpoint_read:
            return {"content": base64.b64encode(b"{not json").decode()}
        if breakage in ("contents_null", "contents_list") and checkpoint_read:
            raw = b"null" if breakage == "contents_null" else b"[]"
            return {"content": base64.b64encode(raw).decode()}
        if breakage == "too_many_pages" and "/pulls?" in path:
            return [dict(gh.prs[0], head=dict(gh.prs[0]["head"], ref="other/x"))] * 100
        return real(self, method, path, token, payload)

    monkeypatch.setattr(FakeGitHub, "__call__", broken)
    with pytest.raises(lc.LifecycleError):
        _gate(gh, monkeypatch)


# --- main(): end-to-end regression ---------------------------------------------


def _run(monkeypatch, tmp_path, gh, offset=280):
    parcels = tmp_path / "parcels.json"
    parcels.write_text(
        json.dumps(
            {
                "features": [
                    {"properties": {"gush": 1, "helka": i}} for i in range(1, 900)
                ]
            }
        )
    )
    calls = []
    monkeypatch.setattr(pf, "gh_api", gh)
    monkeypatch.setattr(pf, "call", lambda *a: calls.append(a) or [])
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)
    monkeypatch.setenv("GH_TOKEN", "fake")
    monkeypatch.setenv("GITHUB_REPOSITORY", SLUG)
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "permit_feed",
            "--parcels",
            str(parcels),
            "--out",
            str(tmp_path / "data" / "permit_requests.json"),
            "--offset",
            str(offset),
            "--limit",
            "280",
            "--checkpoint",
            "--resume",
        ],
    )
    return pf.main(), calls


def _main_feed(tmp_path, batch=MAIN_BEFORE):
    (tmp_path / "data").mkdir(exist_ok=True)
    feed = tmp_path / "data" / "permit_requests.json"
    feed.write_text(json.dumps({"batch": batch, "requests": [{"tik_num": "1/1"}]}))
    return feed


def test_rejected_checkpoint_is_never_resumed_or_republished(monkeypatch, tmp_path):
    # Run 1: a fresh, complete scan writes the feed and its provenance.
    gh = FakeGitHub()
    feed = _main_feed(tmp_path)
    rc, calls = _run(monkeypatch, tmp_path, gh)
    assert rc == 0 and len(calls) == 280
    prov = json.loads((tmp_path / "data" / lc.PROVENANCE_NAME).read_text())
    assert prov["checkpoint_commit"] == gh.branch[0]
    assert prov["batch"] == {"offset": 280, "limit": 280}
    assert prov["source_run"] == "4242"

    # The reviewer closes the data PR unmerged: its head carries that
    # provenance, and main (the next checkout) keeps the old cursor.
    gh.pull(7, "a" * 40)
    gh.files[(lc.PROVENANCE_PATH, "a" * 40)] = prov
    (tmp_path / "data" / lc.PROVENANCE_NAME).unlink()
    _main_feed(tmp_path)
    before_puts, before_feed = len(gh.puts), feed.read_text()

    # Run 2 (same offset): stops before any municipal request.
    rc, calls = _run(monkeypatch, tmp_path, gh)
    assert rc == pf.LIFECYCLE_STOP
    assert calls == []
    assert len(gh.puts) == before_puts  # checkpoint neither resumed nor overwritten
    assert feed.read_text() == before_feed  # nothing to republish
    assert not (tmp_path / "data" / lc.PROVENANCE_NAME).exists()
    assert not any(m in ("DELETE", "PATCH") for m, _ in gh.calls)


def test_merged_checkpoint_lets_the_next_batch_scan(monkeypatch, tmp_path):
    gh = FakeGitHub()
    _main_feed(tmp_path)
    _run(monkeypatch, tmp_path, gh)
    prov = json.loads((tmp_path / "data" / lc.PROVENANCE_NAME).read_text())
    gh.pull(7, "a" * 40, merged=True)
    gh.files[(lc.PROVENANCE_PATH, "a" * 40)] = prov
    _main_feed(tmp_path, {"offset": 280, "limit": 280})  # merged: cursor moved
    rc, calls = _run(monkeypatch, tmp_path, gh, offset=560)
    assert rc == 0 and len(calls) == 280  # new range, fresh scan


def test_lifecycle_api_failure_stops_before_requests(monkeypatch, tmp_path):
    gh = FakeGitHub()
    _checkpoint(gh)
    _main_feed(tmp_path)
    monkeypatch.setattr(
        FakeGitHub, "__call__", lambda *a, **k: {"message": "Bad credentials"}
    )
    rc, calls = _run(monkeypatch, tmp_path, gh)
    assert rc == pf.LIFECYCLE_STOP and calls == []


def test_list_mode_skips_the_gate(monkeypatch, tmp_path):
    # Re-check runs never touch the scan-checkpoint branch (#344), so the
    # gate must not block them either.
    _main_feed(tmp_path)
    plist = tmp_path / "list.json"
    plist.write_text(json.dumps([[1, 1]]))
    parcels = tmp_path / "parcels.json"
    parcels.write_text(
        json.dumps({"features": [{"properties": {"gush": 1, "helka": 1}}]})
    )
    monkeypatch.setattr(
        pf, "gh_api", lambda *a, **k: pytest.fail("no GitHub call in list mode")
    )
    monkeypatch.setattr(pf, "call", lambda *a: [])
    monkeypatch.setattr(pf.time, "sleep", lambda _: None)
    monkeypatch.setenv("GH_TOKEN", "fake")
    monkeypatch.setenv("GITHUB_REPOSITORY", SLUG)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "permit_feed",
            "--parcels",
            str(parcels),
            "--out",
            str(tmp_path / "data" / "permit_requests.json"),
            "--parcel-list",
            str(plist),
        ],
    )
    assert pf.main() == 0
    assert not (tmp_path / "data" / lc.PROVENANCE_NAME).exists()


def test_unchanged_feed_writes_no_provenance(monkeypatch, tmp_path):
    # The publish step opens a PR for any data/ diff; a provenance file
    # alone must never be that diff.
    gh = FakeGitHub()
    feed = _main_feed(tmp_path)
    _run(monkeypatch, tmp_path, gh)
    prov = tmp_path / "data" / lc.PROVENANCE_NAME
    assert prov.exists()
    prov.unlink()
    settled = feed.read_text()
    _checkpoint(gh, sha=OTHER, offset=0, limit=60)  # unrelated, unbound
    rc, _ = _run(monkeypatch, tmp_path, gh)
    assert rc == 0 and feed.read_text() == settled
    assert not prov.exists()


@pytest.mark.parametrize(
    "exc",
    [pf.subprocess.TimeoutExpired("curl", 45), FileNotFoundError("curl")],
)
def test_gate_transport_failure_uses_the_stop_exit(monkeypatch, tmp_path, exc):
    _main_feed(tmp_path)

    def boom(*a, **k):
        raise exc

    rc, calls = _run(monkeypatch, tmp_path, boom)
    assert rc == pf.LIFECYCLE_STOP and calls == []
