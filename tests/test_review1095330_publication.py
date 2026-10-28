"""#580: a fresh page date must not retain an obsolete future publication claim."""
from pathlib import Path

from ginot.page import render_review

ROOT = Path(__file__).resolve().parents[1]


def test_review_source_and_render_have_derived_deadline_and_latest_notice_caveat():
    source = (ROOT / 'plans/101-1095330/analysis/talking_points_101-1095330.md').read_text()
    page = render_review('101-1095330', source, '2026-10-27', 'גינות העיר')
    for text in (source, page):
        assert '2026-10-25' in text
        assert '2026-12-24' in text
        assert 'הפרסום המאוחר בעיתונים' in text
        assert 'ולא מועד רשמי מאומת' in text
        assert 'חלון ההתנגדויות טרם נפתח' not in text
        assert 'יש זמן להיערך' not in text
