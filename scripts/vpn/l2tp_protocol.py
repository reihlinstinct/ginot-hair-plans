"""Pure L2TP configuration, validation and fixed-category diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping


class TunnelError(Exception):
    """Only constant, non-private diagnostics may reach Actions logs."""


def settings(env: Mapping[str, str]) -> tuple[str, str, str, str]:
    server = env.get("VPN_L2TP_SERVER", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", server):
        raise TunnelError("VPN server must be a hostname or IPv4 address, not a URL")
    return (
        server,
        quote(env.get("VPN_L2TP_PSK", "")),
        quote(env.get("VPN_L2TP_USERNAME", "")),
        quote(env.get("VPN_L2TP_PASSWORD", "")),
    )


def quote(value: str) -> str:
    if not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise TunnelError("VPN credential format unsupported")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def configs(server: str, psk: str, user: str, password: str) -> dict[str, str]:
    return {
        "ipsec.conf": f"""config setup
conn mavat-l2tp
    keyexchange=ikev1
    ike=aes256-sha256-modp2048,aes128-sha256-modp2048,aes256-sha1-modp2048,aes128-sha1-modp2048!
    esp=aes256-sha256,aes128-sha256,aes256-sha1,aes128-sha1!
    authby=psk
    type=transport
    left=%defaultroute
    leftprotoport=17/1701
    right={server}
    rightprotoport=17/1701
    forceencaps=yes
    keyingtries=1
    rekey=yes
    rekeymargin=5m
    rekeyfuzz=0%
    ikelifetime=45m
    lifetime=45m
    auto=add
""",
        "ipsec.secrets": ": PSK " + psk + "\n",
        "xl2tpd.conf": f"""[global]
force userspace = yes
port = 1701
[lac mavat]
lns = {server}
ppp debug = no
pppoptfile = /run/mavat-l2tp/ppp-options
length bit = yes
redial = no
""",
        "ppp-options": f"""ipcp-accept-local
ipcp-accept-remote
refuse-eap
refuse-pap
refuse-chap
refuse-mschap
require-mschap-v2
noauth
noccp
nodefaultroute
noipdefault
mtu 1400
mru 1400
maxfail 1
unit 43
name {user}
password {password}
connect-delay 5000
""",
        "strongswan.conf": """charon {
  plugins {
    bypass-lan { load = no }
  }
  syslog {
    daemon { default = -1 }
    auth { default = -1 }
  }
  filelog {
    private_diagnostics {
      path = /run/mavat-l2tp/charon-private.log
      default = 1
      ike = 2
      cfg = 2
      knl = 2
      net = 1
      flush_line = yes
      ike_name = no
      append = no
    }
  }
}
""",
    }


def summarize_negotiation(text: str) -> dict[str, object]:
    """Convert raw private daemon text into fixed categories only, never interpolate."""
    low = text.lower()
    classes = {
        "connection_not_loaded": ("no config named", "no connection named"),
        "daemon_unavailable": (
            "connecting to stroke socket failed",
            "connection refused",
            "charon is not running",
            "starter is not running",
            "failed to connect to",
        ),
        "proposal_mismatch": (
            "no proposal chosen",
            "no_proposal_chosen",
            "no acceptable proposal",
        ),
        "authentication_failed": (
            "authentication failed",
            "authentication_failed",
            "invalid hash",
        ),
        "peer_no_response": ("peer not responding", "giving up after", "retransmit"),
        "ike_established": ("isakmp sa established",),
        "child_established": ("ipsec sa established",),
        "nat_detected": ("behind nat", "nat detected"),
        "nat_t_port_observed": ("[4500]", "port 4500"),
        "kernel_failure": (
            "failed to install",
            "operation not supported",
            "protocol not supported",
        ),
    }
    found = [
        name for name, phrases in classes.items() if any(p in low for p in phrases)
    ]
    if re.search(r"ike_sa[^\n]*established", low):
        found.append("ike_established")
    if re.search(r"child_sa[^\n]*established", low):
        found.append("child_established")
    found = sorted(set(found))
    if re.search(
        r"(?:received|parsed)[^\n]*(?:NO_PROPOSAL_CHOSEN|N\(NO_PROP\))",
        text,
        re.IGNORECASE,
    ):
        found.append("peer_no_proposal_notification")
    sent = re.findall(
        r"generating (ID_PROT|QUICK_MODE|INFORMATIONAL|TRANSACTION)(?:_V1)?[^\n]*?request",
        text,
        re.IGNORECASE,
    )
    parsed = re.findall(
        r"parsed (ID_PROT|QUICK_MODE|INFORMATIONAL|TRANSACTION)(?:_V1)?[^\n]*?(?:request|response)",
        text,
        re.IGNORECASE,
    )
    saw_reply = bool(parsed) or "peer_no_proposal_notification" in found
    return {
        "classes": sorted(set(found)),
        "retransmit_count": len(re.findall(r"\bretransmit\b", low)),
        "generated_request_classes": sorted({x.upper() for x in sent}),
        "parsed_response_classes": sorted({x.upper() for x in parsed}),
        "request_without_observed_response": []
        if saw_reply
        else sorted({x.upper() for x in sent}),
        "peer_reply_observed": saw_reply,
    }


def established_snapshot(status: str) -> dict[str, bool]:
    """Require both an established IKE SA and installed transport CHILD SA."""
    return {
        "ike_sa_established": bool(
            re.search(r"^\s*mavat-l2tp\[\d+\]:\s+ESTABLISHED\b", status, re.MULTILINE)
        ),
        "transport_sa_installed": bool(
            re.search(
                r"^\s*mavat-l2tp\{\d+\}:\s+INSTALLED,\s+TRANSPORT\b",
                status,
                re.MULTILINE,
            )
        ),
    }
