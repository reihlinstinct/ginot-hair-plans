"""#597/#611/#613: newspaper-deposit reviews must not claim a future publication."""
import datetime
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def assert_no_future_publication(root):
    checked = set()
    for path in (root / 'plans').glob('*/plan.json'):
        plan = json.loads(path.read_text())
        if plan.get('land_status') != 'פרסום להפקדה בעיתונים':
            continue
        for review in path.parent.glob('analysis/*.md'):
            # Ignore Markdown emphasis and wrapping, not the claim's meaning.
            normalized = re.sub(r'[\s*_`]+', ' ', review.read_text())
            stale = (
                r'חלון (?:ה)?התנגדויות[^.!?\n]*טרם נפתח'
                r'|פרסום (?:ההפקדה )?בעיתונים[^.!?\n]*(?:עתידי|טרם בוצע)'
            )
            assert not re.search(stale, normalized), str(review)
            checked.add(path.parent.name)
    assert len(checked) >= 2


def test_newspaper_publication_reviews_do_not_claim_future_publication():
    assert_no_future_publication(ROOT)


def test_known_publication_dates_and_caveats():
    for number, date in [('101-1095330', '2026-10-25'), ('101-1386671', '2026-10-16')]:
        text = (ROOT / f'plans/{number}/analysis/talking_points_{number}.md').read_text()
        assert date in text
        assert str(datetime.date.fromisoformat(date) + datetime.timedelta(days=60)) in text
        assert 'ולא מועד רשמי מאומת' in text
        assert 'הפרסום המאוחר בעיתונים' in text


def _fixture(root, phrase='', duplicate_only=False):
    for number in ('101-1095330', '101-1386671'):
        plan = root / 'plans' / number
        (plan / 'analysis').mkdir(parents=True)
        status = 'אחר' if duplicate_only and number == '101-1386671' else 'פרסום להפקדה בעיתונים'
        (plan / 'plan.json').write_text(json.dumps({'land_status': status}))
        for filename in ('talking.md', 'objection.md'):
            (plan / 'analysis' / filename).write_text('פרסום בעיתונים בוצע. חלון ההתנגדויות נפתח.')
    if phrase:
        (root / 'plans/101-1095330/analysis/stale.md').write_text(phrase)


@pytest.mark.parametrize('phrase', [
    'חלון התנגדויות: **טרם נפתח**',
    'פרסום בעיתונים טרם בוצע',
    'פרסום ההפקדה בעיתונים: עתידי',
    'חלון\nההתנגדויות טרם נפתח',
    'חלון ההתנגדויות ' + 'לפי המידע הזמין כעת ' * 8 + 'טרם נפתח',
    'פרסום בעיתונים ' + 'לפי המידע הזמין כעת ' * 8 + 'טרם בוצע',
])
def test_equivalent_formatted_stale_claims_fail(tmp_path, phrase):
    _fixture(tmp_path, phrase)
    with pytest.raises(AssertionError):
        assert_no_future_publication(tmp_path)


def test_review_floor_counts_plans_not_files(tmp_path):
    _fixture(tmp_path, duplicate_only=True)
    with pytest.raises(AssertionError):
        assert_no_future_publication(tmp_path)


def test_current_publication_and_unrelated_future_text_are_allowed(tmp_path):
    _fixture(tmp_path,
             'חלון ההתנגדויות נפתח; פרסום ההפקדה בעיתונים בוצע. פיצוי עתידי דורש בדיקה.')
    assert_no_future_publication(tmp_path)


def test_unit_fixture_does_not_read_repository_docs(tmp_path, monkeypatch):
    def forbidden_read(*args, **kwargs):
        raise AssertionError('unit fixture must not read live repository docs')

    monkeypatch.setattr(Path, 'read_text', forbidden_read)
    _fixture(tmp_path)
