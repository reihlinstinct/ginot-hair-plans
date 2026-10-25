"""Redaction watcher tests (issue #439): the masks are the security boundary."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "vpn_watch_u", ROOT / "scripts/vpn/vpn_watch.py"
)
vw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vw)


@pytest.mark.parametrize(
    "raw,masked",
    [
        ("peer 10.0.0.1/32 responded", "peer <ip> responded"),
        ("v6 fe80::1ff:fe23:4567:890a up", "v6 <ip6> up"),
        ("mac 00:1A:2b:3C:4d:5e seen", "mac <ip6> seen"),  # ipv6 pattern runs first; value still redacted
        ("ESP SPIs: c0a80101_i c0a80102_o", "ESP SPIs: <spi> <spi>"),
        ("ike c0a80101c0a80102_r", "ike <spi>"),
        ("blob abcdef0123456789 end", "blob <hex> end"),
        ("host vpn.example.com ok", "host <host> ok"),
        ("psk=hunter2 set", "psk=<redacted> set"),
        ("username: bob42", "username=<redacted>"),
        ("id 'mavat-l2tp' up", "id '<id>' up"),
        ('cfg "secret value" x', 'cfg "<id>" x'),
    ],
)
def test_mask_redacts_each_private_class(raw, masked):
    assert vw.mask(raw) == masked


def test_mask_keeps_public_structure_words():
    line = "mavat-l2tp[1]: ESTABLISHED 5 minutes ago"
    assert "ESTABLISHED" in vw.mask(line)


def test_filter_events_keeps_only_event_lines_masked():
    lines = [
        "boring keepalive line",
        "retransmit 2 of request to 10.0.0.1",
        "NO_PROPOSAL_CHOSEN notify",
        "plain status",
    ]
    out = vw.filter_events(lines)
    assert out == ["retransmit 2 of request to <ip>", "NO_PROPOSAL_CHOSEN notify"]


def test_filter_status_keeps_sa_lines_only():
    text = "Security Associations (1 up)\n  random junk\n  bytes_i: 100\n"
    out = vw.filter_status(text)
    assert any("Security Associations" in l for l in out)
    assert any("bytes_i" in l for l in out)
    assert not any("random junk" in l for l in out)


def test_run_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("dead")

    monkeypatch.setattr(vw.subprocess, "run", boom)
    assert vw._run("ipsec", "statusall") == "<OSError>"


def test_ppp_states(monkeypatch):
    monkeypatch.setattr(vw, "_run", lambda *a: "")
    assert "DOWN" in vw._ppp()
    monkeypatch.setattr(
        vw, "_run", lambda *a: "3: ppp43: <POINTOPOINT> state UP\n  100 200\n"
    )
    assert "UP" in vw._ppp() and "100" in vw._ppp()


def test_probe_success_and_failure(monkeypatch):
    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(vw.socket, "create_connection", lambda *a, **k: _Sock())
    assert vw._probe().startswith("probe: ok")
    monkeypatch.setattr(
        vw.socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError()),
    )
    assert vw._probe().startswith("probe: FAIL TimeoutError")


def test_main_one_iteration_prints_and_tracks_log(monkeypatch, tmp_path, capsys):
    log = tmp_path / "charon-private.log"
    log.write_text("rekeying SA for 10.9.9.9\nordinary line\n")
    monkeypatch.setattr(vw, "CHARON_LOG", log)
    monkeypatch.setattr(vw, "_run", lambda *a: "")
    monkeypatch.setattr(vw, "_probe", lambda: "probe: ok 1ms")
    ticks = []

    def fake_sleep(n):
        ticks.append(n)
        raise KeyboardInterrupt

    monkeypatch.setattr(vw.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        vw.main()
    out = capsys.readouterr().out
    assert "vpnwatch t+" in out
    assert "charon: rekeying SA for <ip>" in out
    assert "ordinary line" not in out
    assert ticks == [vw.INTERVAL]
