"""Safety pins for the owner-operated L2TP transport (issue #928).

Two properties, both tested with synthetic sentinel values only - no
network, no real credentials, no VPN commands:

1. Import boundary: probe scripts reach the transport only through the
   owner-operated facade scripts/vpn/l2tp.py. A static import scan of
   scripts/ fails if any other module imports l2tp_protocol directly.
2. Redaction regression: the env-supplied secrets (server, PSK, username,
   password) never appear in diagnostics, negotiation summaries, captured
   stdout, or files left behind by a failed connect attempt.
"""

import ast
import importlib.util
import json
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("l2tp_b", ROOT / "scripts/vpn/l2tp.py")
l2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2tp)

# Unique synthetic sentinels: printable (quote() accepts them), shaped so a
# genuine redaction break cannot hide behind a substring of normal output.
SERVER = "sentinel-vpn928-server.example"
PSK = "SentinelPsk928!alpha"
USERNAME = "sentinel_user_928"
PASSWORD = "SentinelPass928#omega"
SENTINELS = [SERVER, PSK, USERNAME, PASSWORD]

ENV = {
    "VPN_L2TP_SERVER": SERVER,
    "VPN_L2TP_PSK": PSK,
    "VPN_L2TP_USERNAME": USERNAME,
    "VPN_L2TP_PASSWORD": PASSWORD,
}


def assert_no_sentinel(text: str, where: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text, f"secret sentinel leaked into {where}"


# Section: Import boundary


def imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_only_the_facade_imports_l2tp_protocol():
    """Probe scripts must not bypass scripts/vpn/l2tp.py (issue #928)."""
    importers = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "scripts").rglob("*.py")
        if "l2tp_protocol" in imported_top_level_modules(path)
    )
    assert importers == ["scripts/vpn/l2tp.py"]


# Section: Redaction in pure helpers


def test_summarize_negotiation_never_echoes_secret_text():
    """Raw daemon text full of secrets becomes fixed categories only."""
    raw = "\n".join(
        [
            f"authentication failed for peer {SERVER} using {PSK}",
            f"retransmit 3 of 5 to {SERVER} (user {USERNAME})",
            f"generating ID_PROT request 0 [ SA ] toward {SERVER}",
            f"parsed QUICK_MODE response 63 from {USERNAME} {PASSWORD}",
        ]
    )
    summary = l2tp.summarize_negotiation(raw)
    # Sanity: the input was really processed, so a clean summary is
    # meaningful rather than vacuous.
    assert summary["classes"]
    assert summary["retransmit_count"] > 0
    assert summary["generated_request_classes"]
    assert summary["peer_reply_observed"] is True
    assert_no_sentinel(json.dumps(summary), "negotiation summary")


def test_error_paths_return_constant_categories_without_secrets():
    """settings/quote/safe_failure diagnostics never interpolate secrets."""
    with pytest.raises(l2tp.TunnelError) as bad_server:
        l2tp.settings({**ENV, "VPN_L2TP_SERVER": "https://" + SERVER + "/x"})
    assert_no_sentinel(str(bad_server.value), "settings() error")

    with pytest.raises(l2tp.TunnelError) as bad_secret:
        l2tp.quote(PSK + "\n")
    assert_no_sentinel(str(bad_secret.value), "quote() error")

    cases = [
        l2tp.TunnelError(PASSWORD),
        OSError(13, PSK),
        subprocess.TimeoutExpired(cmd="ipsec up " + SERVER, timeout=55),
        socket.gaierror(-2, USERNAME),
        ValueError(PSK),
    ]
    for error in cases:
        assert_no_sentinel(l2tp.safe_failure(error), f"safe_failure({type(error)})")


# Section: Redaction through the connect/fail logging path


@pytest.fixture()
def failed_connect(tmp_path, monkeypatch, capsys):
    """Drive connect_bounded to failure with sentinel env and sentinel-laden
    daemon output; return everything an observer could capture."""
    monkeypatch.setattr(
        l2tp.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("192.0.2.43", 0))],
    )
    private_root = tmp_path / "mavat-l2tp"
    monkeypatch.setattr(l2tp, "ROOT", private_root)

    def fake_run(*args: str, check: bool = True) -> str:
        # The daemon echoes secrets into its output; the facade must not.
        raise l2tp.TunnelError("command_exit_1")

    monkeypatch.setattr(l2tp, "run", fake_run)
    old_umask = l2tp.os.umask(0o077)
    try:
        with pytest.raises(l2tp.TunnelError, match="attempts exhausted"):
            l2tp.connect_bounded(ENV, attempts=1)
    finally:
        l2tp.os.umask(old_umask)
    captured = capsys.readouterr()
    return private_root, captured.out + captured.err


def test_connect_failure_output_and_artifacts_carry_no_sentinels(failed_connect):
    private_root, output = failed_connect
    # Sanity: a failure really was reported through the logging path.
    assert '"vpn_failed"' in output
    for line in output.splitlines():
        json.loads(line)  # every emitted line stays machine-readable
    assert_no_sentinel(output, "connect_bounded stdout/stderr")
    assert_no_sentinel(json.dumps(l2tp.DIAGNOSTICS), "module diagnostics")
    assert_no_sentinel(json.dumps(l2tp.READINESS), "module readiness")
    # Failed connects must leave no file behind that quotes a secret:
    # teardown removes the private root, and anything it kept is scanned.
    leftover = (
        ""
        if not private_root.exists()
        else "\n".join(
            path.read_text(errors="replace")
            for path in private_root.rglob("*")
            if path.is_file()
        )
    )
    assert_no_sentinel(leftover, "files left under the private root")


def test_charon_private_log_merge_stays_redacted(tmp_path, monkeypatch, capsys):
    """The best-effort merge of the private charon log into diagnostics
    must also pass through the fixed-category summarizer."""
    monkeypatch.setattr(
        l2tp.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("192.0.2.43", 0))],
    )
    private_root = tmp_path / "mavat-l2tp"
    monkeypatch.setattr(l2tp, "ROOT", private_root)
    calls = {"n": 0}

    def fake_run(*args: str, check: bool = True) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # First up() call (route read): fail the attempt, but only after
            # the private log exists for the merge in connect_bounded.
            private_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            (private_root / "charon-private.log").write_text(
                f"authentication failed {PSK}\nretransmit 1 {PASSWORD}\n"
            )
            raise l2tp.TunnelError("command_exit_1")
        return ""  # teardown commands succeed silently

    monkeypatch.setattr(l2tp, "run", fake_run)
    old_umask = l2tp.os.umask(0o077)
    try:
        with pytest.raises(l2tp.TunnelError, match="attempts exhausted"):
            l2tp.connect_bounded(ENV, attempts=1)
    finally:
        l2tp.os.umask(old_umask)
    captured = capsys.readouterr()
    assert '"vpn_failed"' in captured.out
    diagnostics = json.dumps(l2tp.DIAGNOSTICS)
    # Sanity: the log merge really ran and classified the raw text.
    assert "authentication_failed" in l2tp.DIAGNOSTICS.get("classes", [])
    assert_no_sentinel(diagnostics, "merged diagnostics")
    assert_no_sentinel(captured.out + captured.err, "merged stdout/stderr")
