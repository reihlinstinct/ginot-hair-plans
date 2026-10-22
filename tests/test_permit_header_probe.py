import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "phprobe", Path(__file__).resolve().parents[1] / "scripts/vpn/permit_header_probe.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_only_allowlisted_headers_kept_and_last_response_used():
    raw = ("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nDate: X\r\nLast-Modified: Y\r\n"
           "Set-Cookie: secret=1\r\nX-Forwarded-For: 1.2.3.4\r\nETag: \"e\"\r\n\r\n")
    r = m.parse_headers(raw)
    assert r["status_line"] == "HTTP/1.1 200 OK"
    assert r["headers"] == {"date": "X", "last-modified": "Y", "etag": '"e"'}
    assert "secret" not in str(r) and "1.2.3.4" not in str(r)


def test_empty_dump_is_safe():
    assert m.parse_headers("")["headers"] == {}
