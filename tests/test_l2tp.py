"""Unit tests for the owner-operated L2TP helper (issue #439).

No VPN, network, or root access: subprocess/socket/process boundaries are
mocked. The security-sensitive boundary here is redaction - only constant,
non-private diagnostic categories may leave this module - so those paths are
tested explicitly.
"""
import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("l2tp_u", ROOT / "scripts/vpn/l2tp.py")
l2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2tp)

STATUSALL_LOADED = """
Security Associations (1 up, 0 connecting):
  mavat-l2tp:  %any...vpn.example  IKEv1 Aggressive
"""
STATUSALL_ESTABLISHED = """
Security Associations (1 up, 0 connecting):
  mavat-l2tp[3]: ESTABLISHED 5 minutes ago, 10.0.0.2[me]...10.0.0.1[peer]
  mavat-l2tp{2}: INSTALLED, TRANSPORT, reqid 1, ESP in UDP SPIs: c1_i c2_o
"""


@pytest.fixture(autouse=True)
def clean_module_state():
    l2tp.DIAGNOSTICS.clear()
    l2tp.READINESS.clear()
    l2tp.stage("initializing")
    yield
    l2tp.DIAGNOSTICS.clear()
    l2tp.READINESS.clear()
    l2tp.stage("initializing")


# --- summarize_negotiation: classification is fixed categories only ---------

def test_negotiation_classifies_daemon_unavailable():
    out = l2tp.summarize_negotiation("connecting to stroke socket failed: Connection refused")
    assert "daemon_unavailable" in out["classes"]


def test_negotiation_classifies_proposal_mismatch_and_notification():
    text = "received NO_PROPOSAL_CHOSEN notification\nno proposal chosen"
    out = l2tp.summarize_negotiation(text)
    assert "proposal_mismatch" in out["classes"]
    assert "peer_no_proposal_notification" in out["classes"]
    # a parsed notification counts as a peer reply
    assert out["peer_reply_observed"] is True


def test_negotiation_counts_retransmits_and_pairs_requests():
    text = (
        "generating QUICK_MODE request 1 [ HASH SA No ]\n"
        "parsed QUICK_MODE response 1 [ HASH SA ]\n"
        "generating INFORMATIONAL_V1 request [ HASH N(INITIAL_CONTACT) ]\n"
        "retransmit 2 of request\nretransmit 3 of request\n"
    )
    out = l2tp.summarize_negotiation(text)
    assert out["retransmit_count"] == 2
    assert out["generated_request_classes"] == ["INFORMATIONAL", "QUICK_MODE"]
    assert out["parsed_response_classes"] == ["QUICK_MODE"]
    # the unanswered-request flag is GLOBAL: any observed reply clears it
    assert out["request_without_observed_response"] == []
    assert out["peer_reply_observed"] is True
    # "retransmit" lines classify the exchange as peer_no_response
    assert "peer_no_response" in out["classes"]


def test_negotiation_without_any_reply_flags_all_requests():
    out = l2tp.summarize_negotiation(
        "generating ID_PROT request 0\npeer not responding, giving up after 5 tries"
    )
    assert "peer_no_response" in out["classes"]
    assert out["peer_reply_observed"] is False
    assert out["request_without_observed_response"] == ["ID_PROT"]


def test_negotiation_established_patterns():
    out = l2tp.summarize_negotiation(
        "ike_sa established: 10.0.0.1\nchild_sa established: ts\nIPsec SA established"
    )
    assert "ike_established" in out["classes"]
    assert "child_established" in out["classes"]


def test_negotiation_empty_output_is_empty_categories():
    out = l2tp.summarize_negotiation("")
    assert out["classes"] == []
    assert out["retransmit_count"] == 0
    assert out["peer_reply_observed"] is False


# --- quote / settings: credential and server validation ---------------------

def test_quote_escapes_backslash_and_dquote():
    assert l2tp.quote('a\\b"c') == '"a\\\\b\\"c"'


def test_quote_rejects_empty_and_control_chars():
    with pytest.raises(l2tp.TunnelError):
        l2tp.quote("")
    with pytest.raises(l2tp.TunnelError):
        l2tp.quote("line\nbreak")
    with pytest.raises(l2tp.TunnelError):
        l2tp.quote("nonascii-ג")


def test_settings_rejects_url_and_bad_hosts():
    for bad in ["https://vpn.example", "vpn.example/path", "", "-bad", "a" * 260]:
        with pytest.raises(l2tp.TunnelError):
            l2tp.settings({"VPN_L2TP_SERVER": bad, "VPN_L2TP_PSK": "p",
                           "VPN_L2TP_USERNAME": "u", "VPN_L2TP_PASSWORD": "w"})
    server, psk, _user, _password = l2tp.settings(
        {"VPN_L2TP_SERVER": "vpn.example.com", "VPN_L2TP_PSK": "p",
         "VPN_L2TP_USERNAME": "u", "VPN_L2TP_PASSWORD": "w"}
    )
    assert server == "vpn.example.com"
    assert psk == '"p"'


# --- configs: generated file contents ---------------------------------------

def test_configs_interpolate_server_and_credentials():
    cfgs = l2tp.configs("1.2.3.4", '"psk"', '"user"', '"pass"')
    assert "right=1.2.3.4" in cfgs["ipsec.conf"]
    assert "keyexchange=ikev1" in cfgs["ipsec.conf"]
    assert cfgs["ipsec.secrets"] == ': PSK "psk"\n'
    assert "lns = 1.2.3.4" in cfgs["xl2tpd.conf"]
    assert "name \"user\"" in cfgs["ppp-options"]
    assert "password \"pass\"" in cfgs["ppp-options"]
    assert "unit 43" in cfgs["ppp-options"]
    # auth hardening stays in the generated profile
    assert "require-mschap-v2" in cfgs["ppp-options"]
    assert "private_diagnostics" in cfgs["strongswan.conf"]


# --- status snapshots ---------------------------------------------------------

def test_readiness_snapshot_connection_loaded_regex():
    snap = l2tp.readiness_snapshot(STATUSALL_LOADED)
    assert snap["connection_loaded"] is True
    # no daemon state exists in the test environment
    assert snap["charon_pid_file_present"] is False
    assert snap["charon_process_alive"] is False
    snap2 = l2tp.readiness_snapshot("nothing relevant")
    assert snap2["connection_loaded"] is False


def test_established_snapshot_requires_ike_and_transport():
    both = l2tp.established_snapshot(STATUSALL_ESTABLISHED)
    assert both == {"ike_sa_established": True, "transport_sa_installed": True}
    ike_only = l2tp.established_snapshot("mavat-l2tp[3]: ESTABLISHED 5 minutes ago\n")
    assert ike_only["ike_sa_established"] is True
    assert ike_only["transport_sa_installed"] is False
    assert l2tp.established_snapshot("") == {
        "ike_sa_established": False,
        "transport_sa_installed": False,
    }


# --- run(): subprocess boundary ------------------------------------------------

class _Result:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def test_run_returns_stripped_stdout(monkeypatch):
    monkeypatch.setattr(l2tp.subprocess, "run", lambda *a, **k: _Result(out=" ok \n"))
    assert l2tp.run("echo", "ok") == "ok"


def test_run_raises_constant_diagnostic_on_nonzero(monkeypatch):
    monkeypatch.setattr(
        l2tp.subprocess, "run", lambda *a, **k: _Result(rc=3, err="private detail")
    )
    with pytest.raises(l2tp.TunnelError) as exc:
        l2tp.run("ipsec", "statusall")
    # only the constant category escapes, never the private stderr
    assert str(exc.value) == "command_exit_3"


def test_run_captures_negotiation_diagnostics_in_stage(monkeypatch):
    monkeypatch.setattr(
        l2tp.subprocess,
        "run",
        lambda *a, **k: _Result(rc=0, out="parsed QUICK_MODE response 1\n"),
    )
    l2tp.stage("ipsec_negotiate")
    l2tp.run("timeout", "55", "ipsec", "up", "mavat-l2tp")
    assert l2tp.DIAGNOSTICS["parsed_response_classes"] == ["QUICK_MODE"]
    assert l2tp.DIAGNOSTICS["peer_reply_observed"] is True


# --- safe_failure: redaction boundary ------------------------------------------

def test_safe_failure_maps_known_types():
    assert l2tp.safe_failure(subprocess.TimeoutExpired("cmd", 3)) == "command_timeout"
    assert l2tp.safe_failure(socket.gaierror()) == "dns_resolution_failed"
    assert l2tp.safe_failure(l2tp.TunnelError("command_exit_7")) == "command_exit_7"
    assert (
        l2tp.safe_failure(l2tp.TunnelError("some private detail"))
        == "stage_validation_failed"
    )
    assert l2tp.safe_failure(OSError(13, "denied")) == "os_error_13"
    assert l2tp.safe_failure(ValueError("x")) == "unexpected_error"


# --- wait_ready / require_established ------------------------------------------

def test_wait_ready_raises_when_control_plane_never_ready(monkeypatch):
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: "")
    monkeypatch.setattr(l2tp.time, "sleep", lambda s: None)
    with pytest.raises(l2tp.TunnelError):
        l2tp.wait_ready(limit=2)
    assert l2tp.READINESS["checks"] == 2
    assert l2tp.READINESS["connection_loaded"] is False


def test_wait_ready_succeeds_when_snapshot_ready(monkeypatch):
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: "")
    monkeypatch.setattr(l2tp.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        l2tp,
        "readiness_snapshot",
        lambda status: {
            "charon_pid_file_present": True,
            "charon_process_alive": True,
            "control_socket_present": True,
            "connection_loaded": True,
        },
    )
    l2tp.wait_ready(limit=3)
    assert l2tp.READINESS["checks"] == 1


def test_require_established_raises_until_sa_up(monkeypatch):
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: "nothing up")
    with pytest.raises(l2tp.TunnelError):
        l2tp.require_established()
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: STATUSALL_ESTABLISHED)
    l2tp.require_established()
    assert l2tp.DIAGNOSTICS["ike_sa_established"] is True
    assert l2tp.DIAGNOSTICS["transport_sa_installed"] is True


# --- down(): teardown safety ----------------------------------------------------

def test_down_without_root_dir_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(l2tp, "ROOT", tmp_path / "absent")
    calls = []
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: calls.append(a) or "")
    l2tp.down()
    assert calls == []


def test_down_tears_down_routes_and_cleans_state(monkeypatch, tmp_path):
    root = tmp_path / "mavat-l2tp"
    root.mkdir()
    (root / "state.json").write_text(json.dumps({"server": "1.2.3.4"}))
    monkeypatch.setattr(l2tp, "ROOT", root)
    calls = []
    monkeypatch.setattr(l2tp, "run", lambda *a, **k: calls.append(a) or "")
    l2tp.down()
    flat = [" ".join(c) for c in calls]
    assert any("route del 0.0.0.0/1" in f for f in flat)
    assert any("route del 1.2.3.4/32" in f for f in flat)
    assert any("ipsec down mavat-l2tp" in f for f in flat)
    # every teardown command is best-effort (check=False), never fatal
    assert all(k.get("check") is False for *_, k in
               [(a, {"check": False}) for a in calls])
    assert not root.exists()


# --- connect_bounded: retry policy ----------------------------------------------

def test_connect_bounded_rejects_unsupported_attempt_counts():
    with pytest.raises(l2tp.TunnelError):
        l2tp.connect_bounded({}, attempts=2)


def test_connect_bounded_exhausts_and_forbids_municipal_action(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(l2tp, "ROOT", tmp_path / "absent")
    monkeypatch.setattr(l2tp, "up", lambda env: (_ for _ in ()).throw(OSError(1, "x")))
    monkeypatch.setattr(l2tp, "down", lambda: None)
    monkeypatch.setattr(l2tp.time, "sleep", lambda s: None)
    with pytest.raises(l2tp.TunnelError) as exc:
        l2tp.connect_bounded({}, attempts=3)
    assert "no municipal action permitted" in str(exc.value)
    out = capsys.readouterr().out
    # three bounded failures, two bounded backoffs (60s then 300s)
    assert out.count('"vpn_failed"') == 3
    assert '"seconds": 60' in out and '"seconds": 300' in out
    assert '"diagnostic": "os_error_1"' in out


def test_connect_bounded_succeeds_on_retry(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(l2tp, "ROOT", tmp_path / "absent")
    attempts = {"n": 0}

    def flaky_up(env):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise l2tp.TunnelError("command_exit_2")

    monkeypatch.setattr(l2tp, "up", flaky_up)
    monkeypatch.setattr(l2tp, "down", lambda: None)
    monkeypatch.setattr(l2tp.time, "sleep", lambda s: None)
    l2tp.connect_bounded({}, attempts=3)
    out = capsys.readouterr().out
    assert '"status": "vpn_connected"' in out
    assert '"attempt": 2' in out


def test_connect_bounded_merges_charon_log_diagnostics(monkeypatch, capsys, tmp_path):
    root = tmp_path / "mavat-l2tp"
    root.mkdir()
    (root / "charon-private.log").write_text(
        "generating QUICK_MODE request 1\nretransmit 1 of request\n"
    )
    monkeypatch.setattr(l2tp, "ROOT", root)
    monkeypatch.setattr(
        l2tp, "up", lambda env: (_ for _ in ()).throw(l2tp.TunnelError("command_exit_1"))
    )
    monkeypatch.setattr(l2tp, "down", lambda: None)
    with pytest.raises(l2tp.TunnelError):
        l2tp.connect_bounded({}, attempts=1)
    out = capsys.readouterr().out
    assert '"retransmit_count": 1' in out
    assert '"QUICK_MODE"' in out


# --- main(): entrypoint discipline ----------------------------------------------

def test_main_requires_root(monkeypatch):
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 1000)
    with pytest.raises(SystemExit):
        l2tp.main()


def test_main_rejects_unknown_args(monkeypatch):
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["l2tp.py", "sideways"])
    with pytest.raises(SystemExit):
        l2tp.main()


def test_main_down_invokes_teardown(monkeypatch):
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["l2tp.py", "down"])
    called = []
    monkeypatch.setattr(l2tp, "down", lambda: called.append(True))
    l2tp.main()
    assert called == [True]


def test_main_up_routes_through_connect_bounded(monkeypatch):
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["l2tp.py", "up-bounded"])
    seen = {}
    monkeypatch.setattr(
        l2tp, "connect_bounded", lambda env, n: seen.update(n=n)
    )
    l2tp.main()
    assert seen["n"] == 3


def test_main_up_failure_is_constant_message(monkeypatch):
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["l2tp.py", "up"])

    def boom(env, n):
        raise l2tp.TunnelError("private stage detail")

    monkeypatch.setattr(l2tp, "connect_bounded", boom)
    with pytest.raises(SystemExit) as exc:
        l2tp.main()
    assert "private stage detail" not in str(exc.value)


# --- up(): failure paths carry the failing stage (diagnostics contract) ------

GOOD_ENV = {
    "VPN_L2TP_SERVER": "vpn.example.com",
    "VPN_L2TP_PSK": "p",
    "VPN_L2TP_USERNAME": "u",
    "VPN_L2TP_PASSWORD": "w",
}


def test_up_rejects_bad_settings_at_validate_stage():
    with pytest.raises(l2tp.TunnelError):
        l2tp.up({"VPN_L2TP_SERVER": "https://bad"})
    assert l2tp.STAGE == "validate_settings"


def test_up_dns_failure_at_resolve_stage(monkeypatch, tmp_path):
    monkeypatch.setattr(l2tp, "ROOT", tmp_path / "root")

    def no_dns(*a, **k):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(l2tp.socket, "getaddrinfo", no_dns)
    with pytest.raises(socket.gaierror):
        l2tp.up(GOOD_ENV)
    assert l2tp.STAGE == "resolve_vpn_server"


def test_up_route_pin_failure_at_pin_stage(monkeypatch, tmp_path):
    monkeypatch.setattr(l2tp, "ROOT", tmp_path / "root")
    monkeypatch.setattr(
        l2tp.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("1.2.3.4", 0))],
    )

    def fake_run(*args, **kwargs):
        if args[:2] == ("ip", "-json"):
            return json.dumps([{"gateway": "10.0.0.1", "dev": "eth0"}])
        raise l2tp.TunnelError("command_exit_2")

    monkeypatch.setattr(l2tp, "run", fake_run)
    with pytest.raises(l2tp.TunnelError):
        l2tp.up(GOOD_ENV)
    assert l2tp.STAGE == "pin_transport_route"
