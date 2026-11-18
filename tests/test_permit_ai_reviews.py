"""Permit AI review attachments (issue #1039): every PERMIT_AI_REVIEWS entry
must point at a committed, clearly AI-labelled review page."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ginot.page_permit_policy import PERMIT_AI_REVIEWS

# Section: Attached review targets


def test_every_attached_review_page_exists():
    for tik, url in PERMIT_AI_REVIEWS.items():
        assert (ROOT / "docs" / url).is_file(), f"{tik}: missing docs/{url}"


def test_attached_reviews_are_ai_labelled():
    for tik, url in PERMIT_AI_REVIEWS.items():
        text = (ROOT / "docs" / url).read_text(encoding="utf-8")
        assert "AI" in text, f"{tik}: review page is not labelled as AI"


def test_palmach40a_review_marks_unverified_items():
    """The shimur-7549 review must keep its explicit unverified section and
    must not claim the permit 2024/0215.00 link as fact (#1039 correction)."""
    text = (ROOT / "docs/reviews/palmach40a/review-shimur-7549.html").read_text(
        encoding="utf-8"
    )
    assert "לא מאומת" in text
    assert "7549" in text
    assert "15913" in text
    assert "AI" in text


def test_permit_row_does_not_claim_shimur_review():
    """The 7549 conservation case is only same-parcel with 2024/0215.00:
    the permit row must not link it as the permit's review."""
    assert "2024/0215.00" not in PERMIT_AI_REVIEWS
