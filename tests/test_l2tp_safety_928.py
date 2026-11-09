"""Pin two safety properties of scripts/vpn/ (issue #928).

1. Import boundary: only the transport facade scripts/vpn/l2tp.py may import
   l2tp_protocol. Probes go through the facade.
2. Redaction: the L2TP env settings (server, PSK, username, password) never
   reach diagnostics, negotiation summaries, stdout/stderr or files left
   behind. The secrets only belong in the private daemon configs, which
   teardown deletes.

Stdlib + pytest only. No network, no root, no VPN command is executed: the
subprocess, DNS and filesystem roots are replaced with fakes, and every
credential is a synthetic sentinel.
"""

import ast
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
FACADE = SCRIPTS / "vpn" / "l2tp.py"
PROTOCOL = SCRIPTS / "vpn" / "l2tp_protocol.py"

spec = importlib.util.spec_from_file_location("l2tp_928", FACADE)
l2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2tp)


# Section: Import boundary

# A string that names the module or its file, as importlib would take it.
MODULE_STRING = re.compile(r"[\w./\\-]*\bl2tp_protocol(?:\.py)?")


def protocol_imports(source: str) -> list[str]:
    """Every way a module names l2tp_protocol: import, from-import, importlib."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [
                a.name for a in node.names if a.name.split(".")[-1] == "l2tp_protocol"
            ]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[-1] == "l2tp_protocol":
                found.append(module)
            found += [a.name for a in node.names if a.name == "l2tp_protocol"]
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and MODULE_STRING.fullmatch(node.value)
        ):
            found.append(node.value)  # importlib.import_module("l2tp_protocol")
    return found


@pytest.mark.parametrize(
    "source",
    [
        "import l2tp_protocol",
        "import vpn.l2tp_protocol as p",
        "from l2tp_protocol import settings",
        "from scripts.vpn.l2tp_protocol import quote",
        "from vpn import l2tp_protocol",
        "from . import l2tp_protocol",
        "import importlib\nimportlib.import_module('l2tp_protocol')",
        "spec_from_file_location('x', 'scripts/vpn/l2tp_protocol.py')",
    ],
)
def test_scanner_sees_every_import_form(source):
    assert protocol_imports(source)


def test_scanner_ignores_the_facade_import_and_unrelated_text():
    source = (
        "import l2tp\nfrom l2tp import up\nx = 'l2tp'\n"
        "def f():\n    'Uses l2tp_protocol only through the facade.'\n"
    )
    assert protocol_imports(source) == []


def test_facade_still_imports_the_protocol_module():
    # Positive control: if the facade stops importing it, the boundary test
    # below would pass vacuously.
    assert protocol_imports(FACADE.read_text(encoding="utf-8"))


def test_only_the_facade_imports_l2tp_protocol():
    offenders = {}
    for path in sorted(SCRIPTS.rglob("*.py")):
        if path in (FACADE, PROTOCOL):
            continue
        names = protocol_imports(path.read_text(encoding="utf-8"))
        if names:
            offenders[path.relative_to(REPO).as_posix()] = names
    assert offenders == {}, (
        "probe scripts must use scripts/vpn/l2tp.py, not l2tp_protocol directly"
    )


# Section: Redaction of the L2TP settings

SERVER = "sentinel-server-4c7e.example"
PSK = "SENTINEL-PSK-93c1"
USER = "SENTINEL-USER-5d2e"
PASSWORD = "SENTINEL-PASS-a8b4"
SENTINELS = (SERVER, PSK, USER, PASSWORD)
ENV = {
    "VPN_L2TP_SERVER": SERVER,
    "VPN_L2TP_PSK": PSK,
    "VPN_L2TP_USERNAME": USER,
    "VPN_L2TP_PASSWORD": PASSWORD,
}
# The address the fake DNS returns (TEST-NET-1, never routable).
ADDRESS = "192.0.2.10"


def leaks(text: str) -> list[str]:
    return [s for s in SENTINELS if s in text]


def leaks_in_tree(root: Path) -> dict[str, list[str]]:
    found = {}
    for path in root.rglob("*"):
        if path.is_file():
            hits = leaks(path.read_bytes().decode("utf-8", "replace"))
            if hits:
                found[path.relative_to(root).as_posix()] = hits
    return found


# A daemon that echoes every secret in each line it prints, including the
# lines the classifier matches.
DAEMON_TEXT = "\n".join(
    [
        f"generating ID_PROT_V1 request 0 [ SA V V ] to {SERVER}[500] psk={PSK}",
        f"parsed ID_PROT_V1 response 0 [ SA ] from {SERVER} user {USER}",
        f"generating QUICK_MODE request 1 [ HASH SA No ] pw={PASSWORD}",
        f"retransmit 1 of request with message ID 1 to {SERVER}",
        f"received NO_PROPOSAL_CHOSEN notify for {USER} {PASSWORD}",
        f"authentication failed: invalid HASH for {PSK}",
        f"IKE_SA mavat-l2tp[1] established between me...{SERVER}",
        f"no proposal chosen; behind NAT; port 4500; {USER}:{PASSWORD}",
    ]
)


@pytest.fixture(autouse=True)
def clean_module_state():
    l2tp.DIAGNOSTICS.clear()
    l2tp.READINESS.clear()
    l2tp.stage("initializing")
    yield
    l2tp.DIAGNOSTICS.clear()
    l2tp.READINESS.clear()
    l2tp.stage("initializing")


def test_settings_validation_errors_carry_no_value():
    for env in (
        dict(ENV, VPN_L2TP_SERVER="https://" + SERVER + "/" + PSK),
        dict(ENV, VPN_L2TP_PSK=PSK + "\n"),
        dict(ENV, VPN_L2TP_USERNAME=USER + "\x00"),
        dict(ENV, VPN_L2TP_PASSWORD=PASSWORD + "א"),
    ):
        with pytest.raises(l2tp.TunnelError) as exc:
            l2tp.settings(env)
        assert leaks(str(exc.value)) == []
        assert leaks(repr(exc.value)) == []


def test_negotiation_summary_is_categories_only():
    summary = l2tp.summarize_negotiation(DAEMON_TEXT)
    # The classifier did see the lines (otherwise the check is vacuous) ...
    assert summary["peer_reply_observed"] is True
    assert "authentication_failed" in summary["classes"]
    assert summary["retransmit_count"] == 1
    # ... and kept none of the values in them.
    assert leaks(json.dumps(summary)) == []


def test_snapshots_return_booleans_only():
    text = f"  mavat-l2tp[3]: ESTABLISHED {SERVER} {USER}\n{PSK} {PASSWORD}"
    for value in (
        l2tp.established_snapshot(text),
        l2tp.readiness_snapshot(text),
    ):
        assert all(isinstance(v, bool) for v in value.values())
        assert leaks(json.dumps(value)) == []


def test_configs_confine_each_secret_to_its_private_file():
    _, psk, user, password = l2tp.settings(ENV)
    files = l2tp.configs(ADDRESS, psk, user, password)
    where = {
        s: sorted(name for name, text in files.items() if s in text) for s in SENTINELS
    }
    # The resolved address is used, never the configured hostname.
    assert where == {
        SERVER: [],
        PSK: ["ipsec.secrets"],
        USER: ["ppp-options"],
        PASSWORD: ["ppp-options"],
    }


@pytest.mark.parametrize(
    "error",
    [
        l2tp.TunnelError(f"{SERVER} {PSK} {USER} {PASSWORD}"),
        OSError(13, "denied", f"/etc/{PSK}"),
        subprocess.TimeoutExpired(["ipsec", "up", PASSWORD], 55, output=USER),
        ValueError(PSK),
    ],
)
def test_safe_failure_is_a_constant(error):
    assert leaks(l2tp.safe_failure(error)) == []


class FakeHost:
    """A disposable host: every absolute path is remapped under tmp, and
    every command echoes the secrets back the way a chatty daemon would."""

    def __init__(self, tmp: Path, monkeypatch):
        self.tmp = tmp
        self.commands = []
        self.state_json = []
        real_path = Path

        def remap(*parts):
            path = real_path(*parts)
            if path.is_absolute():
                return real_path(tmp, *path.parts[1:])
            return path

        monkeypatch.setattr(l2tp, "Path", remap)
        monkeypatch.setattr(l2tp, "ROOT", remap("/run/mavat-l2tp"))
        monkeypatch.setattr(l2tp.subprocess, "run", self.run)
        monkeypatch.setattr(
            l2tp.socket,
            "getaddrinfo",
            lambda *a, **k: [(None, None, None, None, (ADDRESS, 0))],
        )
        monkeypatch.setattr(l2tp.time, "sleep", lambda s: None)
        monkeypatch.setattr(l2tp.os, "umask", lambda mask: 0o022)
        # A live local control plane, so the probe reaches the negotiation.
        run_dir = remap("/run")
        run_dir.mkdir(parents=True)
        (run_dir / "charon.pid").write_text(str(os.getpid()))
        (run_dir / "charon.ctl").write_text("")

    def run(self, args, **kwargs):
        args = tuple(args)
        self.commands.append(args)
        out, code = f"echo {SERVER} {PSK} {USER} {PASSWORD}", 0
        if args[:3] == ("ip", "-json", "route"):
            out = json.dumps([{"gateway": "198.51.100.1", "dev": "eth0"}])
        elif args[:2] == ("ipsec", "restart"):
            (l2tp.ROOT / "charon-private.log").write_text(DAEMON_TEXT)
        elif "statusall" in args:
            out = f"  mavat-l2tp:  %any...{SERVER}  IKEv1 {USER}\n"
        elif "up" in args and "ipsec" in args:
            self.state_json.append((l2tp.ROOT / "state.json").read_text())
            out, code = DAEMON_TEXT, 1  # negotiation fails
        return subprocess.CompletedProcess(args, code, out, DAEMON_TEXT)


def test_failed_probe_leaks_nothing_and_leaves_nothing(monkeypatch, capsys, tmp_path):
    host = FakeHost(tmp_path, monkeypatch)
    with pytest.raises(l2tp.TunnelError) as exc:
        l2tp.connect_bounded(ENV, attempts=1)

    # The probe did get as far as the negotiation and the private log merge.
    assert ("timeout", "55", "ipsec", "up", "mavat-l2tp") in host.commands
    assert "authentication_failed" in l2tp.DIAGNOSTICS["classes"]
    captured = capsys.readouterr()
    assert '"vpn_failed"' in captured.out
    assert '"stage": "ipsec_negotiate"' in captured.out

    assert leaks(captured.out + captured.err) == []
    assert leaks(str(exc.value)) == []
    assert leaks(json.dumps([l2tp.DIAGNOSTICS, l2tp.READINESS])) == []
    # The only state file holds the resolved address, not the hostname.
    assert host.state_json == [json.dumps({"server": ADDRESS})]
    # Teardown removed the private configs and log that did hold secrets.
    assert leaks_in_tree(tmp_path) == {}
    assert not l2tp.ROOT.exists()


def test_entrypoint_failure_leaks_nothing(monkeypatch, capsys, tmp_path):
    FakeHost(tmp_path, monkeypatch)
    monkeypatch.setattr(l2tp.os, "geteuid", lambda: 0)
    monkeypatch.setattr(l2tp.os, "environ", dict(ENV))
    monkeypatch.setattr(l2tp.sys, "argv", ["l2tp.py", "up"])
    with pytest.raises(SystemExit) as exc:
        l2tp.main()
    assert (
        str(exc.value) == "Private VPN setup failed; no municipal action is permitted"
    )
    captured = capsys.readouterr()
    assert '"vpn_failed"' in captured.out
    assert leaks(captured.out + captured.err) == []
    assert leaks_in_tree(tmp_path) == {}
