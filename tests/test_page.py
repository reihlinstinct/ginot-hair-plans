from ginot import page


def test_render_site(tmp_path):
    rows = [{"pl_number": "1", "pl_name": "תכנית א", "station_desc": "הפקדה להתנגדויות/השגות",
             "receiving_date": "2026-10-01", "pl_last_deposit_date": "2026-10-10",
             "depositing_date": "", "objection_deadline_derived_60d_from_publication": "2026-12-09",
             "pl_area_dunam": 3.2, "inside_flag": "inside", "mavat_url": "https://mavat.iplan.gov.il/x"}]
    changes = [{"kind": "new", "pl_number": "1", "pl_name": "תכנית א",
                "station_desc": "הפקדה", "mavat_url": "https://mavat.iplan.gov.il/x"}]
    page.render_site(rows, changes, str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "אחרון להתנגדות" in html and "101" not in html  # no crash, hebrew ok
    assert "class='new'" in html
    feed = (tmp_path / "feed.xml").read_text(encoding="utf-8")
    assert "<feed" in feed and "urn:ginot:1" in feed
