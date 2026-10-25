"""Mavat discovery probe tests (issue #439): classification + stop discipline."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "mavat_discover_u", ROOT / "scripts/vpn/mavat_discover.py"
)
md = importlib.util.module_from_spec(spec)
spec.loader.exec_module(md)


class _Out:
    def __init__(self, stdout):
        self.stdout = stdout


def _fake_run(monkeypatch, stdout="200\tapplication/json\t1234"):
    monkeypatch.setattr(md.subprocess, "run", lambda *a, **k: _Out(stdout))


def _body(content: bytes):
    Path("/tmp/probe_body").write_bytes(content)


def test_probe_error_branch_on_exception(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("curl died")

    monkeypatch.setattr(md.subprocess, "run", boom)
    r = md.probe("sv4_page", "https://example.invalid")
    assert r == {"endpoint": "sv4_page", "result": "error", "error_kind": "TimeoutError"}


def test_probe_detects_anti_bot_challenge(monkeypatch):
    _fake_run(monkeypatch, "403\ttext/html\t999")
    _body(b"<html>Incapsula incident _challenge</html>")
    r = md.probe("sv4_page", "https://example.invalid")
    assert r["result"] == "anti_bot_challenge"
    assert r["http"] == "403"


def test_probe_classifies_json_document(monkeypatch):
    _fake_run(monkeypatch, "200\tapplication/json; charset=utf-8\t4321")
    _body(b'{"documents": [{"name": "doc"}]}')
    r = md.probe("rest_plan_documents", "https://example.invalid")
    assert r["result"] == "served"
    assert r["json_like"] is True
    assert r["content_type"] == "application/json"
    assert r["bytes"] == 4321
    assert r["doc_markers"] >= 1


def test_probe_html_shell_is_served_but_not_usable_shape(monkeypatch):
    _fake_run(monkeypatch, "200\ttext/html\t50000")
    _body(b"<html><body>angular shell</body></html>")
    r = md.probe("sv4_page", "https://example.invalid")
    assert r["result"] == "served"
    assert r["json_like"] is False
    assert r["doc_markers"] == 0


def test_probe_missing_body_file_still_classifies(monkeypatch):
    _fake_run(monkeypatch)
    Path("/tmp/probe_body").unlink(missing_ok=True)
    r = md.probe("sv4_page", "https://example.invalid")
    assert r["result"] == "served"


def test_main_stops_on_challenge_with_exit_2(monkeypatch, capsys):
    seq = iter([
        {"endpoint": "a", "result": "served", "json_like": True},
        {"endpoint": "b", "result": "anti_bot_challenge", "http": "403"},
    ])
    monkeypatch.setattr(md, "probe", lambda n, u: next(seq))
    monkeypatch.setattr(md.time, "sleep", lambda s: None)
    assert md.main() == 2
    out = capsys.readouterr().out
    assert '"reason": "challenge_detected"' in out


def test_main_returns_0_with_usable_and_1_without(monkeypatch):
    monkeypatch.setattr(md.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        md, "probe", lambda n, u: {"endpoint": n, "result": "served", "json_like": True}
    )
    assert md.main() == 0
    monkeypatch.setattr(
        md, "probe", lambda n, u: {"endpoint": n, "result": "served", "json_like": False, "doc_markers": 0}
    )
    assert md.main() == 1
