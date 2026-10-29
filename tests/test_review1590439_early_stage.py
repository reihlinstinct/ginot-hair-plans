"""Early-stage review must not imply detailed plan approval (#690)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_review_is_early_stage_and_does_not_forecast_deposit():
    text = (ROOT / 'plans/101-1590439/analysis/talking_points_101-1590439.md').read_text()
    assert 'רעיון מוקדם' in text and 'לא תכנית מפורטת' in text
    assert 'אם וכאשר' in text and 'אין כאן הגשת התנגדות' in text
    assert 'ההפקדה קרובה' not in text and 'בוודאות' not in text
    assert 'לפי המשתמש' not in text


def test_early_stage_plan_is_tracked_without_duplicate():
    data = json.loads((ROOT / 'data/mavat_tracked_plans.json').read_text())
    entries = [p for p in data['plans'] if p['plan_number'] == '101-1590439']
    assert entries == [{'plan_number': '101-1590439', 'mp_id': '1005536258'}]


def test_early_review_banner_does_not_claim_official_documents():
    from ginot.page import render_review
    text = (ROOT / 'plans/101-1590439/analysis/talking_points_101-1590439.md').read_text()
    rendered = render_review('101-1590439', text, '2026-10-29', 'גינות העיר')
    assert 'מתוך מסמכי התכנית הרשמיים' not in rendered
    assert 'לא נבדקה תכנית מפורטת' in rendered
