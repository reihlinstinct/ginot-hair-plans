"""Redacted VPN health watcher for the public Actions log (issue #83).

Runs in the background next to a long VPN job and prints timestamped,
sanitised lines so the exact moment and nature of a tunnel death is
visible even when the run is cancelled (the run log survives a cancel;
an artifact step might not). Nothing is written to a file that is
uploaded, and nothing private is printed: IPv4/IPv6 addresses, MAC
addresses, hostnames, SPIs, identities and anything credential-like are
masked before output.

Per interval it prints:
  * elapsed seconds since the watcher started (= tunnel-up time)
  * IKE SA / CHILD SA state and their ages / rekey timers from
    `ipsec statusall` (addresses masked)
  * ppp interface up/down and byte counters
  * a through-tunnel TCP probe latency (public host, no payload)
  * new charon log lines that mention rekey, DPD, delete, retransmit,
    notify, closing or error events (masked)
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path

CHARON_LOG = Path("/run/mavat-l2tp/charon-private.log")
INTERVAL = 30
PROBE = ("example.com", 80)

_MASKS = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d+)?\b"), "<ip>"),
    (re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b"), "<ip6>"),
    (re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b"), "<mac>"),
    (re.compile(r"\b[0-9a-fA-F]{8}_[io]\b"), "<spi>"),
    (re.compile(r"\bSPIs?[ =:]+[0-9a-fA-F_io]+", re.IGNORECASE), "SPI <spi>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<hex>"),
    (re.compile(r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|il|io|co|me)\b"), "<host>"),
    (re.compile(r"(?i)(psk|password|secret|user(?:name)?|id)\s*[=:]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"'[^']{1,80}'"), "'<id>'"),
    (re.compile(r"\"[^\"]{1,80}\""), '"<id>"'),
]
_EVENT = re.compile(
    r"rekey|dpd|dead peer|delet|retransmit|notify|closing|giving up|"
    r"timeout|error|fail|reauth|expire|lifetime|established|INFORMATIONAL|"
    r"CREATE_CHILD_SA|AUTH_FAILED|NO_PROPOSAL|TS_UNACCEPTABLE",
    re.IGNORECASE,
)
_STATUS_KEEP = re.compile(
    r"ESTABLISHED|INSTALLED|REKEY|rekeying|reauth|Security Associations|"
    r"bytes_i|bytes_o|ago|in [0-9a-f]+|reestablish|lifetime|expire",
    re.IGNORECASE,
)


def mask(text: str) -> str:
    for rx, rep in _MASKS:
        text = rx.sub(rep, text)
    return text


def filter_events(lines: list[str]) -> list[str]:
    return [mask(ln.rstrip()) for ln in lines if _EVENT.search(ln)]


def filter_status(text: str) -> list[str]:
    return [mask(ln.strip()) for ln in text.splitlines() if _STATUS_KEEP.search(ln)]


def _run(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False).stdout
    except Exception as exc:  # noqa: BLE001 - never kill the job
        return f"<{type(exc).__name__}>"


def _ppp() -> str:
    out = _run("ip", "-s", "link", "show", "type", "ppp")
    if not out.strip():
        return "ppp: DOWN (no ppp interface)"
    state = "UP" if "state UP" in out or "UNKNOWN" in out else "DOWN?"
    nums = re.findall(r"^\s+(\d+)\s+(\d+)\s", out, re.MULTILINE)
    return f"ppp: {state} counters(bytes,pkts)={nums[:2]}"


def _probe() -> str:
    t0 = time.monotonic()
    try:
        with socket.create_connection(PROBE, timeout=6):
            return f"probe: ok {int((time.monotonic()-t0)*1000)}ms"
    except Exception as exc:  # noqa: BLE001
        return f"probe: FAIL {type(exc).__name__} after {int(time.monotonic()-t0)}s"


def main() -> None:
    start = time.monotonic()
    offset = 0
    while True:
        el = int(time.monotonic() - start)
        stamp = f"[vpnwatch t+{el//60}m{el%60:02d}s {time.strftime('%H:%M:%S', time.gmtime())}Z]"
        print(stamp, _ppp(), _probe(), flush=True)
        for ln in filter_status(_run("ipsec", "statusall"))[:12]:
            print(stamp, "ipsec:", ln, flush=True)
        try:
            data = CHARON_LOG.read_bytes()
            if len(data) < offset:
                offset = 0
            new = data[offset:].decode(errors="replace").splitlines()
            offset = len(data)
            for ln in filter_events(new)[-40:]:
                print(stamp, "charon:", ln[:240], flush=True)
        except OSError:
            pass
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
