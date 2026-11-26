"""Tests for the single strings document (src/ginot/i18n/strings.json)."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ginot import i18n, page
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
    # #519: the official PD900 deadline note template renders per language
    assert i18n.t(code, "permitsjs.official_deadline") in html


# Section: hreflang alternate links

BASE = "https://example.org/site"


def _hreflang_tags(html):
    return re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]*)">', html)


def test_hreflang_links_lists_every_language_then_x_default():
    tags = _hreflang_tags(i18n.hreflang_links("index.html", BASE))
    expected = [
        (i18n.meta(c)["lang"], BASE + "/" + i18n.page_path(c, "index.html"))
        for c in i18n.lang_codes()
    ] + [("x-default", BASE + "/index.html")]
    assert tags == expected
    langs = [m["lang"] for m in i18n.load()["languages"].values()]
    assert langs == ["he", "en", "ar", "ru", "am", "fr"]


def test_hreflang_links_omitted_without_base_url():
    assert i18n.hreflang_links("index.html", "") == ""
    assert i18n.hreflang_links("index.html") == ""


def test_hreflang_links_normalises_trailing_slash():
    assert i18n.hreflang_links("about.html", BASE + "/") == i18n.hreflang_links(
        "about.html", BASE
    )


def test_hreflang_links_escapes_attributes():
    html = i18n.hreflang_links("index.html", 'https://x.org/?a="b"&c=<d>')
    assert '<link rel="alternate" hreflang="he"' in html
    assert 'href="https://x.org/?a=&quot;b&quot;&amp;c=&lt;d&gt;/index.html"' in html
    assert "&amp;amp;" not in html


def test_hreflang_links_x_default_is_the_hebrew_url():
    tags = {l: h for l, h in _hreflang_tags(i18n.hreflang_links("email.html", BASE))}
    assert tags["x-default"] == tags["he"] == BASE + "/email.html"


def test_no_hreflang_without_base_url_in_renderers():
    from ginot.page import render_index
    from ginot.page_secondary import render_about, render_accessibility

    for html in [
        render_index([_index_row()], [], "2026-11-11", "גינות העיר"),
        render_about("2026-11-11", "גינות העיר"),
        render_accessibility("2026-11-11", "גינות העיר"),
        render_email_page(ROWS, "2026-11-09", "Council"),
    ]:
        assert 'rel="alternate" hreflang=' not in html


@pytest.mark.parametrize("code", i18n.lang_codes())
def test_renderers_emit_all_hreflang_langs_for_each_page(code):
    from ginot.page import render_index
    from ginot.page_secondary import render_about, render_accessibility

    for name, html in [
        (
            "index.html",
            render_index(
                [_index_row()], [], "2026-11-11", "גינות העיר", lang=code, base_url=BASE
            ),
        ),
        ("about.html", render_about("2026-11-11", "גינות העיר", code, base_url=BASE)),
        (
            "accessibility.html",
            render_accessibility("2026-11-11", "גינות העיר", code, base_url=BASE),
        ),
        (
            "email.html",
            render_email_page(ROWS, "2026-11-09", "Council", code, base_url=BASE),
        ),
    ]:
        tags = _hreflang_tags(html)
        expected = [
            (i18n.meta(c)["lang"], BASE + "/" + i18n.page_path(c, name))
            for c in i18n.lang_codes()
        ] + [("x-default", BASE + "/" + name)]
        assert tags == expected, (code, name)


def test_fragments_carry_no_hreflang_tags(tmp_path):
    """Review decision on #966: hreflang belongs in full-document heads only;
    rows/permits fragments are fetched and injected, so they stay clean even
    when base_url is set."""
    from ginot.page import render_index
    from ginot.page_permits import _permits_section

    permits = [{"tik_num": "2026/0001.00", "status": "נפתח תיק רישוי", "gush": 1}]
    a, b = tmp_path / "p.html", tmp_path / "pd.html"
    _permits_section(permits, rows_file=str(a), default_rows_file=str(b))
    rows = tmp_path / "rows.html"
    render_index(
        [_index_row()],
        [],
        "2026-11-11",
        "גינות העיר",
        rows_file=str(rows),
        base_url=BASE,
    )
    for body in (
        a.read_text(encoding="utf-8"),
        b.read_text(encoding="utf-8"),
        rows.read_text(encoding="utf-8"),
    ):
        assert 'rel="alternate" hreflang=' not in body


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


def test_escaped_translated_link_text_and_updated_value(monkeypatch):
    """Issue #965: translated anchor text and the a11y updated stamp must be
    HTML-escaped on output (hostile values must not pass through raw)."""
    doc = json.loads(json.dumps(i18n.load()))
    doc["strings"]["sources.viewer_name"]["he"] = "<b>v</b>"
    doc["strings"]["sources.mavat_name"]["he"] = 'מאב"<script>'
    doc["strings"]["sources.data_dir"]["he"] = "d & <dir>"
    monkeypatch.setattr(i18n, "load", lambda: doc)

    from ginot.page_secondary import render_about, render_accessibility

    about = render_about("2026-11-15", "Council", "he")
    assert _e("<b>v</b>") in about and "<b>v</b>" not in about
    assert _e('מאב"<script>') in about and 'מאב"<script>' not in about
    assert _e("d & <dir>") in about and "d & <dir>" not in about

    hostile = "<i>2026</i>"
    a11y = render_accessibility(hostile, "Council", "he")
    assert _e(hostile) in a11y and hostile not in a11y


def test_col_obj_heading_keeps_base_label_and_marker():
    """#1084: the mixed-aware deadline heading must keep each language's
    base column label AND the ✓ marker it refers to (regression: the am
    value once lost the label entirely)."""
    import json
    import pathlib

    data = json.loads(
        pathlib.Path("src/ginot/i18n/strings.json").read_text(encoding="utf-8")
    )
    base = {
        "he": "אחרון להתנגדות",
        "en": "Last day to object",
        "ar": "آخر يوم للاعتراض",
        "ru": "Последний день возражений",
        "am": "የመቃወሚያ መጨረሻ ቀን",
        "fr": "Dernier jour d'objection",
    }
    values = data["strings"]["index.col_obj"]
    for lang, label in base.items():
        assert label in values[lang], lang
        assert "✓" in values[lang], lang


# Section: label separators live in the templates (#1097)

_URGENT_LABEL_KEYS = [
    "index.urgent_deadline",
    "index.urgent_deadline_verified",
    "indexjs.permit_prefix",
    "indexjs.permit_pubcheck",
    "indexjs.permit_official",
    "indexjs.permit_planned",
]


def test_urgent_list_labels_carry_no_separator():
    """#1097: the label/date separator is the template's job, so these label
    values never carry outer whitespace (a trailing space in the value plus
    the template's separator renders a double space)."""
    data = json.loads(
        (ROOT / "src/ginot/i18n/strings.json").read_text(encoding="utf-8")
    )
    for key in _URGENT_LABEL_KEYS:
        for lang, value in data["strings"][key].items():
            assert value == value.strip(), f"{key}:{lang} carries outer whitespace"


def test_urgent_list_renders_single_separator_per_language():
    """#1097: server render and localized JS both place exactly one space
    between an urgent-list label and the date (regression: the server render
    combined a trailing-space value with the template's space)."""
    from ginot.page import render_index

    row = _index_row()
    row["objection_deadline_derived_2m_from_publication"] = "2026-11-20"
    for code in i18n.lang_codes():
        html = render_index([row], [], "2026-11-11", "גינות העיר", lang=code)
        label = i18n.t(code, "index.urgent_deadline")
        # Server render: the template's single space, never two.
        assert f"{_e(label)} 20.11.26" in html
        assert f"{_e(label)}  20.11.26" not in html
        # Localized JS: the template appends the separator after the value,
        # for every label key (urgent + permit lines), not only the first.
        for key in _URGENT_LABEL_KEYS:
            if key.startswith("indexjs."):
                js_label = json.dumps(i18n.t(code, key), ensure_ascii=False)
                assert js_label + "+' '" in html, f"{code}:{key} lost its separator"
        assert json.dumps(label, ensure_ascii=False) + "+' '" in html


# Section: municipal plan-status labels are translated for display only
def test_plan_status_label_translates_known_and_keeps_unknown():
    assert i18n.plan_status_label("he", "אישור") == "אישור"
    assert i18n.plan_status_label("fr", "אישור") == "Approuvé"
    assert i18n.plan_status_label("ar", "בבדיקה תכנונית") != "בבדיקה תכנונית"
    assert i18n.plan_status_label("fr", "ערך לא מוכר") == "ערך לא מוכר"


def test_every_plan_status_key_exists_in_every_language():
    doc = i18n.load()
    for status, key in i18n.PLAN_STATUS_KEYS.items():
        assert key in doc["strings"], status
        for lang in doc["languages"]:
            assert i18n.t(lang, key).strip(), (status, lang)


def test_permit_status_label_translates_known_and_keeps_unknown():
    assert i18n.permit_status_label("he", "הבקשה נסגרה") == "הבקשה נסגרה"
    assert i18n.permit_status_label("fr", "הבקשה נסגרה") == "Demande clôturée"
    assert i18n.permit_status_label("ru", "סטטוס חדש") == "סטטוס חדש"
    doc = i18n.load()
    for status, key in i18n.PERMIT_STATUS_KEYS.items():
        assert doc["strings"][key]["he"] == status, key


def test_permit_sug_label_translates_known_and_keeps_unknown():
    assert i18n.permit_sug_label("he", "פרגולה") == "פרגולה"
    assert i18n.permit_sug_label("en", "פרגולה") == "Pergola"
    assert i18n.permit_sug_label("ru", "סוג חדש") == "סוג חדש"
    doc = i18n.load()
    for sug, key in i18n.PERMIT_SUG_KEYS.items():
        assert doc["strings"][key]["he"] == sug, key


def test_permit_types_in_data_are_translated():
    """Every permit-request type in the published data has a label, so no
    Hebrew type text is left on the translated permit pages."""
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "data.json").read_text(
            encoding="utf-8"
        )
    )
    permits = data.get("permits") or []
    sugs = {(p.get("sugbakasha") or "") for p in permits} - {""}
    assert sugs, "no permit types found in docs/data.json"
    assert sugs <= set(i18n.PERMIT_SUG_KEYS), sorted(sugs - set(i18n.PERMIT_SUG_KEYS))


def test_permits_js_carries_type_labels_only_for_translated_languages():
    assert "var PSG={}" in page._permits_js("he", "")
    js = page._permits_js("fr", "../")
    assert "var PSG={" in js
    assert i18n.t("fr", i18n.PERMIT_SUG_KEYS["פרגולה"]) in js
