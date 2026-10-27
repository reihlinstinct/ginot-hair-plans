"""#597: no current newspaper-deposit review may claim publication is future."""
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_newspaper_publication_reviews_do_not_claim_future_publication():
    checked = set()
    for path in (ROOT / 'plans').glob('*/plan.json'):
        plan = json.loads(path.read_text())
        if plan.get('land_status') != 'פרסום להפקדה בעיתונים':
            continue
        for review in path.parent.glob('analysis/*.md'):
            text = review.read_text()
            # Ignore Markdown emphasis and wrapping, not the claim's meaning.
            normalized = re.sub(r'[\s*_`]+', ' ', text)
            stale = (
                r'חלון (?:ה)?התנגדויות[^.!?\n]{0,35}טרם נפתח'
                r'|פרסום (?:ההפקדה )?בעיתונים[^.!?\n]{0,35}(?:עתידי|טרם בוצע)'
            )
            assert not re.search(stale, normalized), str(review)
            checked.add(path.parent.name)
    assert len(checked) >= 2
    for number, date in [('101-1095330', '2026-10-25'), ('101-1386671', '2026-10-16')]:
        text = (ROOT / f'plans/{number}/analysis/talking_points_{number}.md').read_text()
        assert date in text
        assert str(datetime.date.fromisoformat(date) + datetime.timedelta(days=60)) in text
        assert 'ולא מועד רשמי מאומת' in text
        assert 'הפרסום המאוחר בעיתונים' in text


def _fixture(root, phrases, duplicate_only=False):
    for number in ('101-1095330', '101-1386671'):
        plan = root / 'plans' / number
        (plan / 'analysis').mkdir(parents=True)
        status = 'אחר' if duplicate_only and number == '101-1386671' else 'פרסום להפקדה בעיתונים'
        (plan / 'plan.json').write_text(json.dumps({'land_status': status}))
        original = (ROOT / f'plans/{number}/analysis/talking_points_{number}.md').read_text()
        (plan / 'analysis' / f'talking_points_{number}.md').write_text(original)
        (plan / 'analysis' / f'objection-points-{number}.md').write_text(original)
    for index, phrase in enumerate(phrases):
        (root / 'plans/101-1095330/analysis' / f'stale{index}.md').write_text(phrase)


def test_equivalent_formatted_stale_claims_fail(tmp_path, monkeypatch):
    import pytest

    phrases = [
        'חלון התנגדויות: **טרם נפתח**',
        'פרסום בעיתונים טרם בוצע',
        'פרסום ההפקדה בעיתונים: עתידי',
        'חלון\nההתנגדויות טרם נפתח',
    ]
    original_root = ROOT
    for index, phrase in enumerate(phrases):
        monkeypatch.setitem(globals(), 'ROOT', original_root)
        root = tmp_path / str(index)
        _fixture(root, [phrase])
        monkeypatch.setitem(globals(), 'ROOT', root)
        with pytest.raises(AssertionError):
            test_newspaper_publication_reviews_do_not_claim_future_publication()


def test_review_floor_counts_plans_not_files(tmp_path, monkeypatch):
    import pytest

    _fixture(tmp_path, [], duplicate_only=True)
    monkeypatch.setitem(globals(), 'ROOT', tmp_path)
    with pytest.raises(AssertionError):
        test_newspaper_publication_reviews_do_not_claim_future_publication()


def test_current_publication_and_unrelated_future_text_are_allowed(tmp_path, monkeypatch):
    _fixture(tmp_path, [
        'חלון ההתנגדויות נפתח; פרסום ההפקדה בעיתונים בוצע. פיצוי עתידי דורש בדיקה.'
    ])
    monkeypatch.setitem(globals(), 'ROOT', tmp_path)
    test_newspaper_publication_reviews_do_not_claim_future_publication()
