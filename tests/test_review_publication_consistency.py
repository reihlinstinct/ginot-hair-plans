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
            text = re.sub(r'(?m)^([ \t]*#{1,6} .*)$', r'\1. ', review.read_text())
            text = re.sub(r'(?m)^([ \t]*(?:[-+*] |#{1,6} |\||> ))', r'. \1', text)
            normalized = re.sub(r'[\s*_`]+', ' ', text)
            # In-token punctuation (dates, URLs, abbreviations) is not a terminator.
            # Missing-space sentence punctuation is conservatively treated as
            # in-token punctuation: it can fail closed and needs human review.
            # Deliberate boundary: a terminal dot after a date ends the claim.
            # Cross-sentence implications still require human review; this guard
            # does not infer that "ב-25.10. טרם" refers to the preceding subject.
            gap = r'(?:[^.!?]|[.!?](?=\S))*'
            stale = (
                rf'חלון (?:ה)?התנגדויות{gap}טרם נפתח'
                rf'|פרסום (?:ההפקדה )?בעיתונים{gap}(?:עתידי|טרם בוצע)'
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
        (plan / 'analysis').mkdir(parents=True, exist_ok=True)
        status = 'אחר' if duplicate_only and number == '101-1386671' else 'פרסום להפקדה בעיתונים'
        (plan / 'plan.json').write_text(json.dumps({'land_status': status}))
        for filename in ('talking.md', 'objection.md'):
            (plan / 'analysis' / filename).write_text('פרסום בעיתונים בוצע. חלון ההתנגדויות נפתח.')
    if phrase:
        (root / 'plans/101-1095330/analysis/stale.md').write_text(phrase)


@pytest.mark.parametrize('phrase', [
    'חלון התנגדויות: **טרם נפתח**',
    'פרסום בעיתונים טרם בוצע',
    'פרסום בעיתונים https://mavat.iplan.gov.il/x טרם בוצע',
    'פרסום בעיתונים https://mavat.iplan.gov.il/x?q=a!b טרם בוצע',
    '> חלון ההתנגדויות טרם נפתח',
    'פרסום ההפקדה בעיתונים ([מקור](https://mavat.iplan.gov.il/x)) טרם בוצע',
    'חלון ההתנגדויות לפי ת.ב.ע המקומית טרם נפתח',
    'פרסום ההפקדה בעיתונים: עתידי',
    'חלון\nההתנגדויות טרם נפתח',
    'חלון_ההתנגדויות טרם נפתח',
    '`פרסום` בעיתונים טרם בוצע',
    '**חלון** ההתנגדויות טרם נפתח',
    'פרסום בעיתונים, שתוכנן ל-16.10.2026, טרם בוצע',
    'חלון ההתנגדויות (60 יום מ-25.10) טרם נפתח',
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


@pytest.mark.parametrize('text', [
    '## חלון ההתנגדויות\n\nלתכנית אחרת: השלב הבא טרם נפתח',
    '> חלון ההתנגדויות: ראו להלן\n> השלב הבא טרם נפתח',
    'חלון ההתנגדויות נפתח; פרסום ההפקדה בעיתונים בוצע. פיצוי עתידי דורש בדיקה.',
    'חלון ההתנגדויות נפתח ב-16.10.2026. השלב הבא טרם נפתח',
    '- חלון ההתנגדויות: ראו להלן\n- סטטוס התכנית: הפקדה; השלב הבא טרם נפתח',
    '| חלון ההתנגדויות: ראו להלן |\n| סטטוס התכנית: הפקדה; השלב הבא טרם נפתח |',
])
def test_current_publication_and_unrelated_future_text_are_allowed(tmp_path, text):
    _fixture(tmp_path, text)
    assert_no_future_publication(tmp_path)


def test_checker_reads_only_the_given_root(tmp_path, monkeypatch):
    _fixture(tmp_path)
    real = Path.read_text

    def guarded(path, *args, **kwargs):
        assert tmp_path.resolve() in path.resolve().parents, path
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', guarded)
    assert_no_future_publication(tmp_path)


def test_terminal_dot_is_a_documented_sentence_boundary(tmp_path):
    _fixture(tmp_path, 'חלון ההתנגדויות ב-25.10. טרם נפתח')
    assert_no_future_publication(tmp_path)


def test_checker_isolation_accepts_symlink_root(tmp_path, monkeypatch):
    actual = tmp_path / 'actual'
    _fixture(actual)
    link = tmp_path / 'linked'
    link.symlink_to(actual, target_is_directory=True)
    test_checker_reads_only_the_given_root(link, monkeypatch)


def test_missing_space_period_conservatively_fails_closed(tmp_path):
    _fixture(tmp_path, 'חלון ההתנגדויות נפתח.השלב הבא טרם נפתח')
    with pytest.raises(AssertionError):
        assert_no_future_publication(tmp_path)
