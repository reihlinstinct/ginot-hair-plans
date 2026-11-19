"""#1052-followup: forum 18.11.2026 source mapping, redaction and non-objection provenance."""

from pathlib import Path

from ginot.page import _community_source_link

ROOT = Path(__file__).resolve().parents[1]


# Section: case mapping


def test_nov18_links_attach_to_both_plans_only():
    for case in ("101-1386671", "101-1348069"):
        assert "forum-2026-11-18-source/summary-redacted.pdf" in _community_source_link(
            case
        )
    assert "forum-2026-11-18-source" not in _community_source_link("101-1377753")
    assert "forum-2026-11-18-source" not in _community_source_link("101-1389568")


# Section: redaction and provenance


def test_source_is_redacted_and_notes_keep_disclaimers():
    pdf = ROOT / "docs/reviews/forum-2026-11-18-source/summary-redacted.pdf"
    assert pdf.stat().st_size > 50000
    for plan in ("101-1386671", "101-1348069"):
        note = (ROOT / f"plans/{plan}/documents/forum-2026-11-18.md").read_text()
        assert "הוסרו פרטי השתתפות" in note and "לא הוגש דבר" in note
        assert "אין לשנות מועד על סמך הסיכום" in note
