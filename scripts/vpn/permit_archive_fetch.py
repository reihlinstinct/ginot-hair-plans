#!/usr/bin/env python3
"""Fetch the public archive documents of ONE permit request through the
owner-operated L2TP tunnel (read-only, public municipal data, no login).

Why: the permit viewer's "optical archive" tab lists the scanned application
and plan sheets of a request, but the archive host answers 403 from outside
Israel. This probe asks the viewer's own API for the archive list of one tik,
then downloads each listed item, slow-paced and serial, and stops on any
anti-bot challenge (exit 2, no workaround).

Privacy contract: the run log is public, so it prints only classification
facts - proc ids, HTTP statuses, byte counts, key NAMES, content types. All
bodies and downloaded files go to a private work directory that the workflow
encrypts to the owner's public GPG key before upload. Nothing from a body is
ever printed.

Env: PROBE_TIK (e.g. 2025/0147.00), optional PROBE_EXTRA_CALLS (JSON list of
{"proc": int, "params": {...}}), optional PROBE_EXTRA_GUIDS (comma list).
Exit codes: 0 done, 2 anti-bot challenge or access denied (stop), 1 other.
"""

import json
import os
import re
import subprocess
import sys
import time

IFACE = "ppp43"
SYS = "26400046"
VIEWER = "https://ykpubdata.jerusalem.muni.il"
API = "https://jerbasicserviceapi.jerusalem.muni.il/api/Db/ExecuteGetJSON"
ARCHIVE_ITEM = "https://jerarchivews.jerusalem.muni.il/api/items/"
WORK = os.environ.get("ARCHIVE_WORK", "/tmp/archive-work")
PACE_SECONDS = 3.0
MAX_ITEMS = 60
MAX_DISCOVERED_PROCS = 8
# 242700447 is the details procedure: it carries owner (baalei inyan) personal
# data and is never called here, same rule as the permit feed.
DENIED_PROCS = frozenset({242700447})
KNOWN_ARCHIVE_PROCS = (242700452, 242700571)
CHALLENGE_MARKERS = (
    b"incapsula",
    b"recaptcha",
    b"captcha",
    b"_challenge",
    b"px-captcha",
    b"perimeterx",
    b"request blocked",
)
GUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)
TIK_RE = re.compile(r"^[0-9]{4}/[0-9]{1,8}(?:\.[0-9]{1,4})?$")
PROC_RE = re.compile(r"\b(24270[0-9]{4})\b")


class Stop(Exception):
    """Challenge or access denied: stop the run, no retry, no workaround."""


def is_challenge(body: bytes, markers: bool = True) -> bool:
    """Access-denied page always; challenge words only when markers=True
    (the viewer's own JS bundle may mention captcha libraries legitimately)."""
    low = body[:200000].lower()
    if b"access denied" in low and b"edgesuite" in low:
        return True
    return markers and any(m in low for m in CHALLENGE_MARKERS)


def find_guids(text: str) -> list[str]:
    """Distinct GUIDs in first-seen order, lower-cased."""
    seen, out = set(), []
    for g in GUID_RE.findall(text):
        g = g.lower()
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def archive_procs_in_bundle(js: str) -> list[int]:
    """Proc ids that sit within 400 characters of an 'archiv' mention."""
    found = []
    for m in PROC_RE.finditer(js):
        window = js[max(0, m.start() - 400) : m.end() + 400].lower()
        proc = int(m.group(1))
        if "archiv" in window and proc not in found and proc not in DENIED_PROCS:
            found.append(proc)
    return found


def shape_of(obj) -> str:
    """Structure only: list length and key NAMES of the first row."""
    if isinstance(obj, list):
        first = obj[0] if obj else None
        keys = sorted(first) if isinstance(first, dict) else []
        return f"list[{len(obj)}] keys={keys}"
    if isinstance(obj, dict):
        return f"dict keys={sorted(obj)}"
    return type(obj).__name__


def tik_variants(tik: str) -> list[str]:
    base = tik.split(".")[0]
    return [tik] if base == tik else [tik, base]


def _curl(url, out, payload=None):
    cmd = [
        "curl", "-s", "-L", "-m", "90", "--max-filesize", "52428800",
        "--interface", IFACE, "-o", out, "-w", "%{http_code} %{content_type}",
        "-H", "Referer: https://ykpubdata.jerusalem.muni.il/",
        "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ]  # fmt: skip
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", payload]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    parts = (res.stdout or "").split(" ", 1)
    status = parts[0] if parts and parts[0].isdigit() else "0"
    ctype = parts[1].strip() if len(parts) > 1 else ""
    return int(status), ctype


def _guard(path, markers=True):
    with open(path, "rb") as f:
        body = f.read()
    if is_challenge(body, markers):
        raise Stop("anti_bot_challenge_or_access_denied")
    return body


def api_call(proc, params, label):
    out = f"{WORK}/api_{label}.bin"
    payload = json.dumps({"Cnn": "cnnGisYk", "ProcName": proc, "Parameters": params})
    status, _ = _curl(API, out, payload)
    body = _guard(out) if os.path.exists(out) else b""
    try:
        shape = shape_of(json.loads(body))
    except (ValueError, UnicodeDecodeError):
        shape = "non-json"
    print(f"call proc={proc} label={label} status={status} bytes={len(body)} {shape}")
    time.sleep(PACE_SECONDS)
    return body


def discover_procs():
    """Download the viewer bundle (public JS) and list archive-related procs."""
    os.makedirs(f"{WORK}/bundle", exist_ok=True)
    index = f"{WORK}/bundle/index.html"
    status, _ = _curl(VIEWER + "/", index)
    html = (
        _guard(index, markers=False).decode("utf-8", "replace")
        if os.path.exists(index)
        else ""
    )
    scripts = sorted(set(re.findall(r"/static/js/[A-Za-z0-9._-]+\.js", html)))
    print(f"viewer page status={status} scripts={len(scripts)}")
    procs: list[int] = []
    for i, src in enumerate(scripts[:6]):
        out = f"{WORK}/bundle/js{i}.js"
        status, _ = _curl(VIEWER + src, out)
        js = (
            _guard(out, markers=False).decode("utf-8", "replace")
            if os.path.exists(out)
            else ""
        )
        for p in archive_procs_in_bundle(js):
            if p not in procs:
                procs.append(p)
        time.sleep(PACE_SECONDS)
    print(f"archive-related procs in bundle: {procs}")
    return procs


def main():
    tik = os.environ.get("PROBE_TIK", "").strip()
    if not TIK_RE.fullmatch(tik):
        print("PROBE_TIK must look like 2025/0147.00")
        return 1
    os.makedirs(WORK, exist_ok=True)
    try:
        procs = [p for p in discover_procs() if p not in KNOWN_ARCHIVE_PROCS]
        calls = []
        for t in tik_variants(tik):
            calls.append((242700452, {"sysId": SYS, "tikNum": t}))
            calls.append((242700571, {"sysId": "26400056", "tikNum": t}))
        for p in procs[:MAX_DISCOVERED_PROCS]:
            calls.append((p, {"sysId": SYS, "tikNum": tik}))
            calls.append((p, {"systemCode": SYS, "tikNum": tik}))
        extra = os.environ.get("PROBE_EXTRA_CALLS", "").strip()
        if extra:
            for item in json.loads(extra):
                if int(item["proc"]) not in DENIED_PROCS:
                    calls.append((int(item["proc"]), dict(item["params"])))
        guids: list[str] = []
        for n, (proc, params) in enumerate(calls):
            body = api_call(proc, params, f"{n}_{proc}")
            for g in find_guids(body.decode("utf-8", "replace")):
                if g not in guids:
                    guids.append(g)
        for g in os.environ.get("PROBE_EXTRA_GUIDS", "").split(","):
            g = g.strip().lower()
            if GUID_RE.fullmatch(g) and g not in guids:
                guids.append(g)
        print(f"archive item ids found: {len(guids)}")
        for n, g in enumerate(guids[:MAX_ITEMS]):
            out = f"{WORK}/item_{n:02d}_{g}.bin"
            status, ctype = _curl(ARCHIVE_ITEM + g, out)
            size = os.path.getsize(out) if os.path.exists(out) else 0
            if size and size < 200000:
                _guard(out)
            print(f"item {n:02d} status={status} bytes={size} type={ctype[:40]}")
            time.sleep(PACE_SECONDS)
    except Stop as exc:
        print(f"STOP: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
