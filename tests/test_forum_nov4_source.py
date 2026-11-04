"""#848: case mapping, source separation and non-objection provenance."""

from pathlib import Path

from ginot.page import _community_source_link, _permit_review_cell

ROOT = Path(__file__).resolve().parents[1]


def test_nov4_links_do_not_replace_october_or_ai_review():
    for case in ("101-1377753", "101-1488261", "2026/0439.00"):
        assert "forum-2026-11-04-source/summary-redacted.pdf" in _community_source_link(
            case
        )
    assert _community_source_link("101-1377753").count("community-source") == 2
    assert "forum-2026-11-04-source" not in _community_source_link("101-1389568")
    assert "forum-2026-11-04-source" not in _community_source_link("1993/0664.03")
    cell = _permit_review_cell("2026/0439.00")
    assert "סקירת AI</a>" in cell and "04.11.26" in cell


def test_source_note_preserves_no_objection_and_date_uncertainty():
    note = (ROOT / "plans/101-1488261/documents/forum-2026-11-04.md").read_text()
    assert "החליט לא להתנגד" in note and "לא הוראת המשתמש" in note
    note = (ROOT / "plans/101-1377753/documents/forum-2026-11-04.md").read_text()
    assert "17.11.2026" in note and "60 יום" in note and "נדרש בירור" in note
    pdf = ROOT / "docs/reviews/forum-2026-11-04-source/summary-redacted.pdf"
    assert pdf.stat().st_size > 50000
