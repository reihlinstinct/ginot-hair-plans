import importlib.util
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location("permit_enrich", vpn / "permit_enrich.py")
permit_enrich = importlib.util.module_from_spec(spec)
spec.loader.exec_module(permit_enrich)


def req(tik, status, **kw):
    r = {"tik_num": tik, "status": status}
    r.update(kw)
    return r


def test_select_tiks_diff_only():
    reqs = [req("1", "נפתח תיק רישוי"), req("2", "נפתח תיק רישוי"),
            req("3", "הבקשה נסגרה")]
    sel = permit_enrich.select_tiks(reqs, {"1", "3"}, include_unenriched=False)
    assert sel == ["1"]  # terminal tik 3 excluded even when in the diff


def test_select_tiks_include_unenriched():
    reqs = [req("1", "נפתח תיק רישוי", publication_start="2026-01-01"),
            req("2", "נפתח תיק רישוי"),
            req("3", "הבקשה נסגרה")]
    sel = permit_enrich.select_tiks(reqs, set(), include_unenriched=True)
    assert sel == ["2"]  # already-enriched and terminal tiks skipped
