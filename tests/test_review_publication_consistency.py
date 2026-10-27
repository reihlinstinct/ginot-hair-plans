"""#597: no current newspaper-deposit review may claim publication is future."""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_newspaper_publication_reviews_do_not_claim_future_publication():
    checked = 0
    for path in (ROOT / 'plans').glob('*/plan.json'):
        plan = json.loads(path.read_text())
        if plan.get('land_status') != 'פרסום להפקדה בעיתונים':
            continue
        for review in path.parent.glob('analysis/*.md'):
            text = review.read_text()
            assert 'פרסום בעיתונים עתידי' not in text, str(review)
            assert 'חלון ההתנגדויות טרם נפתח' not in text, str(review)
            checked += 1
    assert checked >= 2
    for number, date in [('101-1095330', '2026-10-25'), ('101-1386671', '2026-10-16')]:
        text = (ROOT / f'plans/{number}/analysis/talking_points_{number}.md').read_text()
        assert date in text
        assert str(datetime.date.fromisoformat(date) + datetime.timedelta(days=60)) in text
        assert 'ולא מועד רשמי מאומת' in text
        assert 'הפרסום המאוחר בעיתונים' in text
