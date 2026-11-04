"""#845: community material is linked only to the actual three cases."""

from pathlib import Path

from ginot.page import _community_source_link, _permit_review_cell

ROOT = Path(__file__).resolve().parents[1]


def test_exact_cases_and_permit_not_plan():
    for case in ("101-1389568", "101-1377753", "1993/0664.03"):
        assert "summary-redacted.pdf" in _community_source_link(case)
        assert "לא הודעה רשמית" in _community_source_link(case)
    assert _community_source_link("101-1488261") == ""
    assert _community_source_link("1993/0664.02") == ""
    assert "summary-redacted.pdf" in _permit_review_cell("1993/0664.03")
    assert "סקירת AI</a>" not in _permit_review_cell("1993/0664.03")


def test_sources_are_available_without_deadline_rewrite():
    assert (
        ROOT / "docs/reviews/forum-2026-10-14/summary-redacted.pdf"
    ).stat().st_size > 100000
    for case in ("101-1389568", "101-1377753"):
        note = (ROOT / f"plans/{case}/documents/forum-2026-10-14.md").read_text()
        assert "אינן ממצאים מאומתים" in note
    note = (ROOT / "plans/101-1377753/documents/forum-2026-10-14.md").read_text()
    assert "17.11.2026" in note and "18.11.2026" in note
    assert "דורש בדיקת הודעת" in note
