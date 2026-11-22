"""Archive-fetch probe: pure helpers and the workflow's privacy contract.

No network and no tunnel: the helpers are exercised on literals, and the
workflow file is read as text. The contract under test is that the public run
log carries no body content and that nothing but an encrypted archive is
uploaded.
"""

import base64
import datetime
import hashlib
import importlib.util
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location(
    "permit_archive_fetch", ROOT / "scripts/vpn/permit_archive_fetch.py"
)
pf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pf)
WORKFLOW = (ROOT / ".github/workflows/permit-archive-fetch.yml").read_text()


# Section: helpers
def test_find_guids_dedups_and_lowercases():
    text = "x 16E57A23-0D2B-464C-ACAD-30895F07B87D y 16e57a23-0d2b-464c-acad-30895f07b87d z"
    assert pf.find_guids(text) == ["16e57a23-0d2b-464c-acad-30895f07b87d"]


def test_archive_procs_need_an_archive_word_nearby_and_skip_denied():
    js = "a" * 500 + "getArchivList:{ProcName:242700460}" + "b" * 500
    js += "c" * 500 + "ProcName:242700461" + "d" * 500
    js += "archiv ProcName:242700447"
    assert pf.archive_procs_in_bundle(js) == [242700460]


def test_shape_prints_key_names_never_values():
    shape = pf.shape_of([{"name": "SECRET", "id": 1}])
    assert shape == "list[1] keys=['id', 'name']"
    assert "SECRET" not in shape
    assert pf.shape_of({"a": 1}) == "dict keys=['a']"


def test_challenge_detection():
    assert pf.is_challenge(b"<html>Please solve this CAPTCHA</html>")
    assert pf.is_challenge(b"Access Denied ... errors.edgesuite.net", markers=False)
    assert not pf.is_challenge(b"var x='recaptcha';", markers=False)
    assert not pf.is_challenge(b"[]")


def test_tik_format_and_variants():
    assert pf.TIK_RE.fullmatch("2025/0147.00")
    assert not pf.TIK_RE.fullmatch("2025/0147.00; rm -rf /")
    assert pf.tik_variants("2025/0147.00") == ["2025/0147.00", "2025/0147"]
    assert pf.tik_variants("2025/0147") == ["2025/0147"]


def test_details_procedure_with_personal_data_is_never_called():
    assert 242700447 in pf.DENIED_PROCS


# Section: workflow privacy contract
def test_workflow_uploads_only_the_encrypted_archive_and_metadata_log():
    block = WORKFLOW.split("Upload the encrypted archive")[1].split("Tear down")[0]
    assert "archive.tar.gz.gpg" in block and "fetch-log.txt" in block
    assert "archive-work" not in block
    assert "retention-days: 3" in block


def test_workflow_pins_the_owner_key_and_encrypts_before_upload():
    assert "03849178BB0FB05C2FA910074B3E57844FE3F041" in WORKFLOW
    enc = WORKFLOW.index("--encrypt")
    assert enc < WORKFLOW.index("upload-artifact")
    assert "sudo rm -rf /tmp/archive-work" in WORKFLOW


def test_dispatch_inputs_reach_the_script_through_env_only():
    run_lines = [ln for ln in WORKFLOW.splitlines() if "${{ inputs" in ln]
    assert all(ln.strip().startswith("PROBE_") for ln in run_lines)
    assert (
        "sudo --preserve-env=PROBE_TIK,PROBE_EXTRA_CALLS,PROBE_EXTRA_GUIDS "
        "python3 scripts/vpn/permit_archive_fetch.py"
    ) in WORKFLOW


# Section: stop statuses and discovered procs are never called
def test_plain_denial_statuses_stop_the_run():
    for status in (401, 403, 429, 503):
        with pytest.raises(pf.Stop):
            pf._stop_on_status(status)
    pf._stop_on_status(200)
    pf._stop_on_status(404)


def test_discover_procs_stops_on_viewer_and_bundle_denial(monkeypatch, tmp_path):
    # #954: both _stop_on_status calls in discover_procs must fire. A denial
    # on the viewer page stops before any bundle script is requested; a denial
    # on a bundle script stops before its procs are read.
    monkeypatch.setattr(pf, "WORK", str(tmp_path))
    monkeypatch.setattr(pf.time, "sleep", lambda *_: None)
    requested = []

    def curl_viewer_denied(url, out, payload=None):
        requested.append(url)
        Path(out).write_text("<html></html>")
        return 403, "text/html"

    monkeypatch.setattr(pf, "_curl", curl_viewer_denied)
    with pytest.raises(pf.Stop):
        pf.discover_procs()
    assert len(requested) == 1

    requested.clear()

    def curl_bundle_denied(url, out, payload=None):
        requested.append(url)
        if url.endswith("/"):
            Path(out).write_text('<script src="/static/js/main.abc.js"></script>')
            return 200, "text/html"
        Path(out).write_text("var x=1;")
        return 429, "text/html"

    monkeypatch.setattr(pf, "_curl", curl_bundle_denied)
    with pytest.raises(pf.Stop):
        pf.discover_procs()
    assert len(requested) == 2


def test_discovered_procs_are_listed_not_called(monkeypatch, capsys):
    # Behavioural, not source-text (#954): run main with a bundle that
    # "discovers" an unknown stored procedure and assert api_call never
    # receives it - an unknown proc may return personal data.
    called = []

    def fake_api_call(proc, params, label):
        called.append(proc)
        return b"{}"

    monkeypatch.setattr(pf, "api_call", fake_api_call)
    monkeypatch.setattr(pf, "discover_procs", lambda: [242709999])
    monkeypatch.setattr(pf.time, "sleep", lambda *_: None)
    monkeypatch.setenv("PROBE_TIK", "2025/0147.00")
    monkeypatch.delenv("PROBE_EXTRA_CALLS", raising=False)
    monkeypatch.delenv("PROBE_EXTRA_GUIDS", raising=False)
    assert pf.main() == 0
    assert 242709999 not in called
    # The known archive procs ran: 2 tik variants x 2 known procs.
    assert called == [242700452, 242700571] * 2
    assert "listed, not called" in capsys.readouterr().out


# Section: the committed recipient key matches the pinned fingerprint
PINNED_KEY_FPR = "03849178BB0FB05C2FA910074B3E57844FE3F041"


def _dearmor(text: str) -> bytes:
    b64: list[str] = []
    in_body = False
    for line in text.splitlines():
        if line.startswith("-----BEGIN"):
            in_body = True
            continue
        if line.startswith(("-----END", "=")):
            break
        if not in_body or not line.strip() or (":" in line and not b64):
            continue
        b64.append(line.strip())
    return base64.b64decode("".join(b64))


def _packets(data: bytes):
    i = 0
    while i < len(data):
        first = data[i]
        i += 1
        assert first & 0x80, "not an OpenPGP packet"
        if first & 0x40:  # new format
            tag = first & 0x3F
            o = data[i]
            i += 1
            if o < 192:
                ln = o
            elif o < 224:
                ln = ((o - 192) << 8) + data[i] + 192
                i += 1
            else:
                assert o == 255, "partial body length not expected in a key file"
                ln = struct.unpack(">I", data[i : i + 4])[0]
                i += 4
        else:  # old format
            tag = (first >> 2) & 0x0F
            lt = first & 0x03
            assert lt != 3, "indeterminate length not expected in a key file"
            width = (1, 2, 4)[lt]
            fmt = (">B", ">H", ">I")[lt]
            ln = struct.unpack(fmt, data[i : i + width])[0]
            i += width
        body = data[i : i + ln]
        i += ln
        yield tag, body


def _v4_fingerprint(body: bytes) -> str:
    blob = b"\x99" + struct.pack(">H", len(body)) + body
    return hashlib.sha1(blob).hexdigest().upper()


def _self_sig_expiry(sig_body: bytes, creation: int):
    """Key-expiration-time subpacket (type 9) of a v4 self-signature."""
    if not sig_body or sig_body[0] != 4:
        return None
    hlen = struct.unpack(">H", sig_body[4:6])[0]
    subs = sig_body[6 : 6 + hlen]
    j = 0
    while j < len(subs):
        o = subs[j]
        j += 1
        if o < 192:
            ln = o
        elif o < 255:
            ln = ((o - 192) << 8) + subs[j] + 192
            j += 1
        else:
            ln = struct.unpack(">I", subs[j : j + 4])[0]
            j += 4
        stype = subs[j]
        j += 1
        data = subs[j : j + ln - 1]
        j += ln - 1
        if stype == 9:
            return creation + struct.unpack(">I", data)[0]
    return None


def _recipient_key_packets():
    key = (ROOT / "scripts/vpn/archive-recipient.pub.asc").read_text(encoding="utf-8")
    return list(_packets(_dearmor(key)))


def test_recipient_key_file_is_public_and_present():
    key = (ROOT / "scripts/vpn/archive-recipient.pub.asc").read_text(encoding="utf-8")
    assert key.startswith("-----BEGIN PGP PUBLIC KEY BLOCK-----")
    assert "PRIVATE" not in key
    assert "scripts/vpn/archive-recipient.pub.asc" in WORKFLOW


def test_recipient_key_fingerprint_matches_pinned():
    """#956: compute the v4 fingerprint (SHA-1 over 0x99||len||key packet)
    and pin it, so a silent key swap fails the suite."""
    packets = _recipient_key_packets()
    assert packets and packets[0][0] == 6, "first packet must be a public key"
    assert _v4_fingerprint(packets[0][1]) == PINNED_KEY_FPR


def test_recipient_key_has_no_secret_packets():
    """#956: no secret-key (5) or secret-subkey (7) packets in the file."""
    tags = [t for t, _ in _recipient_key_packets()]
    assert 5 not in tags and 7 not in tags, "secret key material committed"


def test_recipient_key_expiry_warned_ahead():
    """#956: expiry-warning - when the key carries an expiration it must be
    more than 90 days out, so rotation happens before the archive breaks."""
    packets = _recipient_key_packets()
    creation = struct.unpack(">I", packets[0][1][1:5])[0]
    expiry = None
    for tag, body in packets[1:]:
        if tag == 2:
            expiry = _self_sig_expiry(body, creation)
            if expiry:
                break
    if expiry is None:
        return  # no expiry set on the current key; nothing to warn about
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    days = (expiry - now) // 86400
    assert days > 90, (
        f"recipient key expires in {days} days - rotate and re-pin the fingerprint"
    )
