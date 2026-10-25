"""Header-probe parsing tests (issue #439): allowlist is the privacy boundary."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "permit_header_probe_u", ROOT / "scripts/vpn/permit_header_probe.py"
)
hp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hp)


DUMP = (
    "HTTP/1.1 100 Continue\r\n\r\n"
    "HTTP/1.1 200 OK\r\n"
    "Date: Tue, 25 Oct 2026 05:00:00 GMT\r\n"
    "ETag: \"abc123\"\r\n"
    "X-Private-Internal: secret\r\n"
    "Set-Cookie: session=xyz\r\n"
    "Last-Modified: Mon, 24 Oct 2026 10:00:00 GMT\r\n"
)


def test_parse_headers_uses_last_block_and_allowlist():
    Path("/tmp/hdr").write_text(DUMP, encoding="latin-1")
    info = hp.parse_headers(Path("/tmp/hdr").read_text(encoding="latin-1"))
    assert info["status_line"].startswith("HTTP/1.1 200")
    assert info["headers"]["etag"] == '"abc123"'
    assert info["headers"]["last-modified"].startswith("Mon, 24 Oct")
    # privacy boundary: non-allowlisted headers never leave the function
    assert "x-private-internal" not in info["headers"]
    assert "set-cookie" not in info["headers"]


def test_parse_headers_empty_dump():
    info = hp.parse_headers("")
    assert info["status_line"] == ""
    assert info["headers"] == {}


class _Out:
    stdout = ""


def test_call_returns_none_on_challenge(monkeypatch, capsys):
    monkeypatch.setattr(hp.subprocess, "run", lambda *a, **k: _Out())
    Path("/tmp/body").write_bytes(b"px-captcha perimeterx block page")
    Path("/tmp/hdr").write_text("HTTP/1.1 403 Forbidden\n")
    assert hp.call("search", []) is None
    assert '"anti_bot_challenge"' in capsys.readouterr().out


def test_call_logs_allowlisted_only(monkeypatch, capsys):
    monkeypatch.setattr(hp.subprocess, "run", lambda *a, **k: _Out())
    Path("/tmp/body").write_bytes(b'{"Results": []}')
    Path("/tmp/hdr").write_text(DUMP.replace("\r\n", "\n"))
    info = hp.call("search", [])
    out = capsys.readouterr().out
    assert info is not None and info["call"] == "search"
    assert "session=xyz" not in out and "secret" not in out
    assert "abc123" in out


def test_main_flows(monkeypatch):
    # challenge on first call -> 2
    monkeypatch.setattr(hp, "call", lambda tag, extra: None)
    assert hp.main() == 2
    # no last-modified/date -> 0 after one call
    monkeypatch.setattr(
        hp, "call", lambda tag, extra: {"headers": {}, "call": tag}
    )
    assert hp.main() == 0
    # last-modified present -> conditional call happens
    calls = []

    def fake_call(tag, extra):
        calls.append(tag)
        return {"headers": {"last-modified": "Mon, 24 Oct 2026"}, "call": tag}

    monkeypatch.setattr(hp, "call", fake_call)
    assert hp.main() == 0
    assert calls == ["search", "conditional"]
