"""Conservation committee cases: validation and the collapsed index section."""

import copy
import re
from pathlib import Path

from ginot import conservation as cons
from ginot import i18n

ROOT = Path(__file__).resolve().parents[1]
OK = cons.load(ROOT / "data/conservation_cases.json")[0]


def _t(key):
    return i18n.t("he", key)


# Section: Data file


def test_shipped_cases_are_valid_and_point_at_real_review_pages():
    cases = cons.load(ROOT / "data/conservation_cases.json")
    assert cases and cons.validate(cases) == []
    for c in cases:
        assert (ROOT / "docs" / c["review_path"]).exists()


def test_validation_rejects_bad_records():
    for key, bad in (
        ("plan_ref", "101-1"),
        ("source_url", "http://example.org/x"),
        ("review_path", "../secret.html"),
        ("meeting_date", "25.01.2026"),
    ):
        c = copy.deepcopy(OK) | {key: bad}
        assert cons.validate([c]), key
    extra = copy.deepcopy(OK) | {"tik_num": "2024/0215.00"}
    assert cons.validate([extra])  # no permit link field allowed
    assert cons.validate([OK, OK])  # duplicate case_id


# Section: Rendering


def test_section_is_collapsed_escaped_and_not_linked_to_a_plan_or_permit():
    c = copy.deepcopy(OK) | {"address": "<b>x</b>"}
    out = cons.render_section([c], _t, "")
    assert 'id="conservation-panel"' in out and " open" not in out.split(">")[0]
    assert "&lt;b&gt;" in out and "<b>x</b>" not in out
    assert "review-shimur-7549.html" in out and OK["source_url"] in out
    assert not re.search(r"101-\d|\d{4}/\d{4}\.\d\d", out)
    assert cons.render_section([], _t, "") == ""
    assert cons.render_section([{"case_id": "1"}], _t, "") == ""


def test_every_language_has_the_conservation_strings():
    keys = [k for k in i18n.load()["strings"] if k.startswith("conservation.")]
    assert len(keys) == 8
    for lang in i18n.lang_codes():
        for k in keys:
            assert i18n.load()["strings"][k].get(lang), (lang, k)
