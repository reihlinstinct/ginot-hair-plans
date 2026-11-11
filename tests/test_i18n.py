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
        assert m["label"] == m["label"].strip() and 2 <= len(m["label"]) <= 3, code
    labels = [m["label"] for m in doc["languages"].values()]
    assert len(set(labels)) == len(labels), "language labels must be unique"
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
        "label": "ES",
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
    assert ">ES</option>" in i18n.switcher("en", "email.html")


def test_switcher_is_a_select_whose_options_come_from_the_document():
    root = i18n.switcher("he", "email.html")
    assert '<select id="lang-select"' in root and '<label for="lang-select">' in root
    opts = re.findall(
        r'<option value="([^"]*)" lang="([^"]*)" title="([^"]*)"( selected)?>([^<]*)</option>',
        root,
    )
    assert [o[4] for o in opts] == [i18n.meta(c)["label"] for c in i18n.lang_codes()]
    assert [o[2] for o in opts] == [i18n.meta(c)["name"] for c in i18n.lang_codes()]
    assert [o[1] for o in opts] == [i18n.meta(c)["lang"] for c in i18n.lang_codes()]
    assert [o[0] for o in opts] == ["email.html"] + [
        f"{c}/email.html" for c in i18n.lang_codes() if c != "he"
    ]
    assert [bool(o[3]) for o in opts] == [c == "he" for c in i18n.lang_codes()]
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
    assert f'href="{pre}{i18n.page_path(code, "index.html")}"' in html
    assert "{generated}" not in html


def test_hebrew_page_is_unchanged_in_key_markers():
    html = render_email_page(ROWS, "2026-11-09", "Council")
    assert "<title>קבלת מייל על תוכנית - Council</title>" in html
    assert 'value="he"' in html and "draft-note" not in html


# Section: the main pages render in every language


def _index_row():
    return {
        "pl_number": "101-1",
        "pl_name": "תכנית 1",
        "station_desc": "הפקדה",
        "receiving_date": "",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_2m_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_index_page_renders_in_every_language(code):
    from ginot.page import render_index

    permits = [
        {
            "tik_num": "2026/0439.00",
            "status": "בבדיקה",
            "mahut": "מ",
            "sugbakasha": "היתר",
        }
    ]
    html = render_index(
        [_index_row()], [], "2026-11-11", "גינות העיר", permits=permits, lang=code
    )
    m = i18n.meta(code)
    assert f'<html dir="{m["dir"]}" lang="{m["lang"]}">' in html
    assert ('class="draft-note"' in html) == i18n.is_draft(code)
    pre = i18n.asset_prefix(code)
    assert f'href="{pre}style.css"' in html
    assert "{generated}" not in html
    # permits table mobile labels are translated data-label attributes
    assert f"data-label='{_e(i18n.t(code, 'permits.col_address'))}'" in html
    # data values (plan names, permit statuses) stay Hebrew in every language
    assert "תכנית 1" in html and "בבדיקה" in html
    # the table fragments are per-language and load from next to the page,
    # never from the Hebrew root (#961 review)
    assert "fetch('rows.html')" in html
    assert "fetch('permits.html')" in html
    assert "fetch('permits-default.html')" in html
    assert "fetch('../rows.html')" not in html
    assert "fetch('../permits.html')" not in html
    assert "fetch('../permits-default.html')" not in html
    # shared data is fetched from the root
    assert f"fetch('{pre}publications_active.json')" in html
    # review and source links point at the root reviews tree from every language
    assert f"href='{pre}reviews/palmach41/review-2026-0439.00.html'" in html


# Section: the mail API reads the same document
def test_api_languages_come_from_the_document():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "send_plan_email", ROOT / "api" / "send_plan_email.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.LANGS) == set(i18n.lang_codes())


def test_vercelignore_ships_the_strings_document():
    """The mail API reads strings.json at runtime, so .vercelignore must not
    drop it with the rest of src/ (checked with git's own ignore rules)."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        (Path(d) / ".gitignore").write_text((ROOT / ".vercelignore").read_text())
        kept = "src/ginot/i18n/strings.json"
        dropped = ["src/ginot/page.py", "src/ginot/i18n/__init__.py"]
        for rel in [kept, *dropped]:
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text("x")

        def ignored(rel):
            r = subprocess.run(["git", "-C", d, "check-ignore", "-q", rel], check=False)
            return r.returncode == 0

        assert not ignored(kept)
        assert all(ignored(x) for x in dropped)
