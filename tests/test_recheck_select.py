import importlib.util
import pathlib
import sys

vpn = pathlib.Path(__file__).parent.parent / "scripts" / "vpn"
sys.path.insert(0, str(vpn))
spec = importlib.util.spec_from_file_location(
    "recheck_select", vpn / "recheck_select.py"
)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def req(tik, status, g, h, checked=""):
    return {
        "tik_num": tik,
        "status": status,
        "gush": g,
        "helka": h,
        "details_checked_on": checked,
    }


def test_active_tier_picks_only_parcels_with_changeable_requests():
    reqs = [
        req("1", "נפתח תיק רישוי", 1, 1),
        req("2", "הבקשה נסגרה", 1, 1),
        req("3", "הבקשה נסגרה", 2, 2),
        req("4", "הוכנה טיוטת היתר בניה", 3, 3),
    ]
    assert rs.active_parcels(reqs) == [(1, 1)]


def test_rotation_orders_never_checked_then_oldest_and_caps():
    parcels = [(1, 1), (2, 2), (3, 3), (4, 4)]
    reqs = [
        req("1", "הבקשה נסגרה", 1, 1, "2026-10-01"),
        req("2", "הבקשה נסגרה", 2, 2, "2026-09-01"),
        req("3", "נפתח תיק רישוי", 3, 3, "2026-10-20"),
    ]
    # (3,3) is active, (4,4) has no rows = never checked
    assert rs.rotation_parcels(reqs, parcels, 4, 10) == [(4, 4), (2, 2), (1, 1)]
    assert rs.rotation_parcels(reqs, parcels, 4, 2) == [(4, 4), (2, 2)]


def test_rotation_leaves_unreached_parcels_to_the_main_scan():
    parcels = [(1, 1), (2, 2), (3, 3)]
    assert rs.rotation_parcels([], parcels, 2, 10) == [(1, 1), (2, 2)]


def test_status_sets_match_permit_enrich():
    spec2 = importlib.util.spec_from_file_location(
        "permit_enrich", vpn / "permit_enrich.py"
    )
    pe = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(pe)
    assert rs.TERMINAL_STATUSES == pe.TERMINAL_STATUSES
    assert rs.LATE_STAGE_STATUSES == pe.LATE_STAGE_STATUSES


def test_stale_before_returns_only_unchecked_active_parcels_oldest_first():
    reqs = [
        req("1", "נפתח תיק רישוי", 1, 1, "2026-10-22"),
        req("2", "נפתח תיק רישוי", 2, 2, "2026-10-01"),
        req("3", "נפתח תיק רישוי", 3, 3, ""),
        req("4", "הבקשה נסגרה", 4, 4, ""),
    ]
    assert rs.active_parcels(reqs, "2026-10-22") == [(3, 3), (2, 2)]
    assert rs.active_parcels(reqs, "2026-10-22", cap=1) == [(3, 3)]
    # once everything was checked today the daily run has nothing to do
    assert (
        rs.active_parcels(
            [req("1", "נפתח תיק רישוי", 1, 1, "2026-10-22")], "2026-10-22"
        )
        == []
    )


def test_all_parcels_of_skips_incomplete_and_sorts():
    geo = {
        "features": [
            {"properties": {"gush": 30030, "helka": 12}},
            {"properties": {"gush": 30025, "helka": 126}},
            {"properties": {"gush": 30025}},  # missing helka
            {"properties": {}},
            {"properties": {"gush": 30025, "helka": 40}},
        ]
    }
    assert rs.all_parcels_of(geo) == [(30025, 40), (30025, 126), (30030, 12)]


def _write_feed(tmp_path, requests, offset=0, limit=0):
    import json as _json

    feed = tmp_path / "feed.json"
    feed.write_text(_json.dumps(
        {"requests": requests, "batch": {"offset": offset, "limit": limit}}
    ))
    return str(feed)


def _write_parcels(tmp_path, pairs):
    import json as _json

    geo = tmp_path / "parcels.geojson"
    geo.write_text(_json.dumps(
        {"features": [{"properties": {"gush": g, "helka": h}} for g, h in pairs]}
    ))
    return str(geo)


def test_main_active_tier_with_stale_before_and_cap(tmp_path, capsys, monkeypatch):
    import json as _json

    feed = _write_feed(tmp_path, [
        req("1", "נפתח תיק רישוי", 1, 1, "2026-09-01"),
        req("2", "נפתח תיק רישוי", 2, 2, "2026-10-20"),
        req("3", "הבקשה נסגרה", 3, 3, ""),
    ])
    monkeypatch.setattr(
        "sys.argv",
        ["recheck_select.py", "--tier", "active", "--feed", feed,
         "--stale-before", "2026-10-01", "--cap", "5"],
    )
    rs.main()
    assert _json.loads(capsys.readouterr().out) == [[1, 1]]


def test_main_rotation_tier_uses_scan_cursor(tmp_path, capsys, monkeypatch):
    import json as _json

    feed = _write_feed(tmp_path, [
        req("1", "הבקשה נסגרה", 1, 1, "2026-10-01"),
        req("2", "נפתח תיק רישוי", 2, 2, "2026-10-20"),
    ], offset=1, limit=1)
    parcels = _write_parcels(tmp_path, [(1, 1), (2, 2), (3, 3)])
    monkeypatch.setattr(
        "sys.argv",
        ["recheck_select.py", "--tier", "rotation", "--feed", feed,
         "--parcels", parcels, "--cap", "10"],
    )
    rs.main()
    # cursor = offset+limit = 2 -> only (1,1),(2,2) scanned; (2,2) active excluded
    assert _json.loads(capsys.readouterr().out) == [[1, 1]]
