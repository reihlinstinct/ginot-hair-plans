def test_permit_heading_has_no_rollout_draft_label():
    from ginot.page import _permits_section

    html = _permits_section([{"tik_num": "2026/0001.00", "status": "הוכנה טיוטת היתר בניה"}])
    assert "<h2>בקשות היתר</h2>" in html
    assert "טיוטה - DRAFT" not in html
    assert "הוכנה טיוטת היתר בניה" in html
    assert "סיום פרסום מתוכנן אינו מועד התנגדות מאומת" in html


def test_published_permit_heading_matches_source():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "docs/index.html").read_text()
    assert "<h2>בקשות היתר</h2>" in html
    assert "<h2>בקשות היתר (טיוטה - DRAFT)</h2>" not in html
