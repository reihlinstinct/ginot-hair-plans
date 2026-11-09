"""Tests for the single strings document (src/ginot/i18n/strings.json)."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ginot import i18n
from ginot.page_email import render_email_page
from ginot.page_resources import _e

ROWS = [{"pl_number": "101-1", "pl_name": "Alpha", "_open_obj": True}]


# Section: the document is the only list of languages
def test_document_is_complete_for_every_language():
    doc = i18n.load()
    assert doc["default"] in doc["languages"]
    for code, m in doc["languages"].items():
        assert m["dir"] in ("rtl", "ltr"), code
        assert m["lang"] and m["name"], code
    for key, entry in doc["strings"].items():
        assert set(entry) == set(doc["languages"]), (
            f"{key}: translations {sorted(entry)} != languages "
            f"{sorted(doc['languages'])}"
        )
        assert all(isinstance(v, str) and v.strip() for v in entry.values()), key


def test_rtl_languages_are_he_and_ar_only():
    rtl = {c for c in i18n.lang_codes() if i18n.direction(c) == "rtl"}
    assert rtl == {"he", "ar"}


def test_placeholders_match_across_languages():
    for key, entry in i18n.load()["strings"].items():
        names = {
            lang: set(re.findall(r"\{(\w+)\}", text)) for lang, text in entry.items()
        }
        assert len({frozenset(v) for v in names.values()}) == 1, (key, names)


def test_no_language_list_in_code_outside_the_document():
    """A language code list in the generator or page code would defeat the
    one-file rule. The API function keeps its own mail strings for now."""
    codes_literal = re.compile(r"""\[\s*["']he["']\s*,\s*["']en["']""")
    for path in (ROOT / "src" / "ginot").rglob("*.py"):
        assert not codes_literal.search(path.read_text(encoding="utf-8")), path


# Section: behaviour derived from the document
def test_fallback_to_default_when_a_language_has_no_entry(monkeypatch):
    doc = json.loads(json.dumps(i18n.load()))
    del doc["strings"]["email.submit"]["fr"]
    monkeypatch.setattr(i18n, "load", lambda: doc)
    assert i18n.t("fr", "email.submit") == doc["strings"]["email.submit"]["he"]
    assert i18n.t("xx", "email.submit") == doc["strings"]["email.submit"]["he"]
    assert i18n.meta("xx") == i18n.meta("he")


def test_new_language_added_to_the_document_flows_everywhere(monkeypatch):
    doc = json.loads(json.dumps(i18n.load()))
    doc["languages"]["es"] = {
        "name": "Español",
        "lang": "es",
        "dir": "ltr",
        "draft": True,
    }
    for entry in doc["strings"].values():
        entry["es"] = "ES " + entry["en"]
    monkeypatch.setattr(i18n, "load", lambda: doc)
    html = render_email_page(ROWS, "2026-11-09", "Council", "es")
    assert 'lang="es"' in html and "Español" in html
    assert '<option value="../es/email.html"' in i18n.switcher("en", "email.html")
    assert "es" in i18n.lang_codes()


def test_switcher_is_a_select_whose_options_come_from_the_document():
    root = i18n.switcher("he", "email.html")
    assert '<select id="lang-select"' in root and '<label for="lang-select">' in root
    opts = re.findall(r'<option value="([^"]*)" lang="([^"]*)"( selected)?>', root)
    assert [o[1] for o in opts] == [i18n.meta(c)["lang"] for c in i18n.lang_codes()]
    assert [o[0] for o in opts] == ["email.html"] + [
        f"{c}/email.html" for c in i18n.lang_codes() if c != "he"
    ]
    assert [bool(o[2]) for o in opts] == [c == "he" for c in i18n.lang_codes()]
    en = i18n.switcher("en", "email.html")
    assert '<option value="../email.html"' in en
    assert '<option value="../ar/email.html"' in en
    assert '<option value="en/email.html"' not in en
    assert "<noscript>" in en and 'href="../ar/email.html"' in en


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_email_page_renders_in_every_language(code):
    html = render_email_page(ROWS, "2026-11-09", "Council", code)
    m = i18n.meta(code)
    assert f'<html dir="{m["dir"]}" lang="{m["lang"]}">' in html
    assert f'name="lang" value="{code}"' in html
    assert _e(i18n.t(code, "email.submit")) in html
    assert ('class="draft-note"' in html) == i18n.is_draft(code)
    pre = i18n.asset_prefix(code)
    assert f'href="{pre}style.css"' in html
    assert "{generated}" not in html


def test_hebrew_page_is_unchanged_in_key_markers():
    html = render_email_page(ROWS, "2026-11-09", "Council")
    assert "<title>קבלת מייל על תוכנית - Council</title>" in html
    assert 'value="he"' in html and "draft-note" not in html
