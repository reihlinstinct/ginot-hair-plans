import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "vpn_watch", pathlib.Path(__file__).parents[1] / "scripts/vpn/vpn_watch.py")
vw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vw)


def test_mask_removes_addresses_and_ids():
    s = "sending to 203.0.113.7[500] host vpn.example.com id 'alice' psk=abc123 SPIs 1a2b3c4d_i fe80::1 aa:bb:cc:dd:ee:ff"
    out = vw.mask(s)
    for leak in ("203.0.113.7", "vpn.example.com", "alice", "abc123", "1a2b3c4d", "fe80::1", "aa:bb:cc"):
        assert leak not in out


def test_event_filter_keeps_rekey_and_dpd_only():
    lines = ["15[IKE] sending DPD request to 1.2.3.4", "00[LIB] loaded plugins: aes", "09[CHD] rekeying CHILD_SA"]
    out = vw.filter_events(lines)
    assert len(out) == 2 and all("1.2.3.4" not in x for x in out)


def test_status_filter_masks():
    t = "mavat[1]: ESTABLISHED 12 minutes ago, 10.0.0.5[x]...203.0.113.7[y]\nnoise line"
    out = vw.filter_status(t)
    assert out and "203.0.113.7" not in out[0] and "10.0.0.5" not in out[0]
