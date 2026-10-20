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


def test_backfill_skips_late_stages_by_default():
    reqs = [req("1", "נפתח תיק רישוי"),
            req("2", "הוכנה טיוטת היתר בניה"),
            req("3", "שולמה מקדמה"),
            req("4", "נדונה בוועדת המשנה")]
    sel = permit_enrich.select_tiks(reqs, set(), include_unenriched=True)
    assert sel == ["1", "4"]
    wide = permit_enrich.select_tiks(reqs, set(), True, include_late_stages=True)
    assert wide == ["1", "2", "3", "4"]


def test_diff_tiks_fetched_even_in_late_stage():
    reqs = [req("2", "הוכנה טיוטת היתר בניה")]
    assert permit_enrich.select_tiks(reqs, {"2"}, include_unenriched=False) == ["2"]


def test_backfill_request_file_is_valid():
    import json
    path = pathlib.Path(__file__).parent.parent / "data" / "backfill_request.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    assert d["mode"] in ("scan", "enrich")
    assert isinstance(d["include_unenriched"], bool) and isinstance(d["include_late_stages"], bool)
    assert int(d["limit"]) > 0 and int(d["offset"]) >= 0
    assert d["request_id"]


def test_count_only_prints_selection_without_fetching(tmp_path, capsys, monkeypatch):
    import json
    mirror = tmp_path / "mirror.json"
    reqs = [req("1", "נפתח תיק רישוי", publication_start="2026-01-01"),
            req("2", "נפתח תיק רישוי"),
            req("3", "הבקשה נסגרה"),
            req("4", "הוכנה טיוטת היתר בניה")]
    mirror.write_text(json.dumps({"requests": reqs}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["permit_enrich.py", "--mirror", str(mirror),
                                      "--diff", str(tmp_path / "missing.json"),
                                      "--include-unenriched", "--count-only"])
    assert permit_enrich.main() == 0
    assert capsys.readouterr().out.strip() == "1"  # only tik 2; diff file absent
    # count-only must not modify the mirror file
    assert "publication_start" not in json.loads(mirror.read_text(encoding="utf-8"))["requests"][1]
