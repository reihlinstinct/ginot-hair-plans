"""Site languages and UI strings, read from one document (strings.json).

strings.json is the only place that lists languages: their display names,
html lang, text direction and whether the translation is still a machine
draft. Language selectors, dir/lang attributes, page paths and the fallback
all derive from it, so adding a language means adding it to that one file
(tests check it is complete). Hebrew is the default and the fallback.
"""

import json
from functools import lru_cache
from html import escape
from pathlib import Path

STRINGS_PATH = Path(__file__).with_name("strings.json")


@lru_cache(maxsize=1)
def load() -> dict:
    with open(STRINGS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def default_lang() -> str:
    return load()["default"]


def lang_codes() -> list[str]:
    """Language codes in document order (the order of the selector)."""
    return list(load()["languages"])


def meta(lang: str) -> dict:
    languages = load()["languages"]
    return languages.get(lang) or languages[default_lang()]


def direction(lang: str) -> str:
    return meta(lang)["dir"]


def is_draft(lang: str) -> bool:
    return bool(meta(lang).get("draft"))


def draft_note(lang: str) -> str:
    """The machine-translation notice shown on draft-language pages (''
    for Hebrew)."""
    m = meta(lang)
    if not m.get("draft"):
        return ""
    return (
        f'<p class="draft-note" lang="{escape(m["lang"])}">'
        f"{escape(t(lang, 'ui.draft_note'))}</p>"
    )


def t(lang: str, key: str, **fmt) -> str:
    """The string for key in lang; falls back to the default language when
    that language has no entry. An unknown key is a programming error."""
    entry = load()["strings"][key]
    text = entry.get(lang) or entry[default_lang()]
    return text.format(**fmt) if fmt else text


def js_snippet(lang: str, keys: list[str]) -> str:
    """Inline <script> exposing strings to the static JS files: window.GINOT_I18N
    maps key to this language's text (the files keep their Hebrew literals as
    fallback) and window.GINOT_BASE is the relative prefix back to the site
    root, for fetches of shared JSON/vendor assets from a per-language page.
    The keys are site strings, so the values never contain "</"."""
    data = json.dumps({k: t(lang, k) for k in keys}, ensure_ascii=False)
    base = json.dumps(asset_prefix(lang))
    return f"<script>window.GINOT_I18N={data};window.GINOT_BASE={base};</script>"


def asset_prefix(lang: str) -> str:
    """Relative prefix from a page of lang back to the site root."""
    return "" if lang == default_lang() else "../"


def page_path(lang: str, name: str) -> str:
    """Path of page name for lang, from the site root (default at the root)."""
    return name if lang == default_lang() else f"{lang}/{name}"


_SWITCH_JS = """(function(){var s=document.getElementById('lang-select');
if(!s)return;var cur=s.getAttribute('data-current'),pending=null,mouse=false;
function go(v){if(v&&v!==cur){location.href=v;}}
function reset(){s.value=cur;pending=null;}
reset();
window.addEventListener('pageshow',reset);
s.addEventListener('pointerdown',function(){mouse=true;});
s.addEventListener('keydown',function(e){
mouse=false;
if(e.key==='Enter'){go(pending||s.value);}
else if(e.key==='Escape'){reset();}});
s.addEventListener('change',function(){
if(mouse||document.activeElement!==s){go(s.value);}else{pending=s.value;}mouse=false;});
s.addEventListener('blur',function(){if(pending){go(pending);}mouse=false;});
})();"""


def hreflang_links(name: str, base_url: str = "") -> str:
    """Absolute <link rel="alternate" hreflang="..."> tags for page name.

    One per language in lang_codes() order, then x-default pointing at the
    default-language (root) URL. hreflang needs absolute URLs, so this is
    base_url (stripped of trailing slashes) + '/' + page_path(lang, name);
    x-default uses the default language's path. Attributes are escaped with
    html.escape, matching the project's _e escaping elsewhere. With an
    empty base_url, return "" (no tags), mirroring how _social_meta skips
    og:url without a base_url, so existing callers/tests are unaffected.
    """
    if not base_url:
        return ""
    base = base_url.rstrip("/")
    tags = [
        f'<link rel="alternate" hreflang="{escape(meta(code)["lang"])}" '
        f'href="{escape(base + "/" + page_path(code, name))}">'
        for code in lang_codes()
    ]
    tags.append(
        f'<link rel="alternate" hreflang="x-default" '
        f'href="{escape(base + "/" + page_path(default_lang(), name))}">'
    )
    return "\n".join(tags)


def switcher(lang: str, name: str) -> str:
    """The language selector for page name: a drop-down whose options come
    from the document. Mouse and touch navigate on selection; keyboard users
    move through the options and confirm with Enter (or by leaving the
    field), so arrow keys and type-ahead do not trigger navigation. Without JavaScript the
    same languages show as plain links."""
    options, links = [], []
    for code in lang_codes():
        m = meta(code)
        href = escape(asset_prefix(lang) + page_path(code, name))
        sel = " selected" if code == lang else ""
        options.append(
            f'<option value="{href}" lang="{escape(m["lang"])}" '
            f'title="{escape(m["name"])}"{sel}>{escape(m["label"])}</option>'
        )
        links.append(
            f'<a href="{href}" hreflang="{escape(m["lang"])}" '
            f'lang="{escape(m["lang"])}">{escape(m["name"])}</a>'
        )
    label = escape(t(lang, "ui.language"))
    here = escape(asset_prefix(lang) + page_path(lang, name))
    return (
        f'<nav class="lang-switch" aria-label="{label}">'
        f'<label for="lang-select">{label}</label> '
        f'<select id="lang-select" autocomplete="off" data-current="{here}">'
        + "".join(options)
        + "</select>"
        f"<noscript> {' &middot; '.join(links)}</noscript>"
        f"<script>{_SWITCH_JS}</script></nav>"
    )


# Municipal plan-status strings (data values) that have a translated label.
# The raw value stays in data-status and in filtering; only the shown text
# changes. A value not listed here is shown as the source gives it.
PLAN_STATUS_KEYS = {
    "אישור": "planstatus.approved",
    "בבדיקה תכנונית": "planstatus.review",
    "במילוי תנאים להפקדה": "planstatus.conditions",
    "הפקדה להתנגדויות/השגות": "planstatus.deposit_obj",
    "הפקדה להתנגדויות": "planstatus.deposit_obj2",
    "הפקדה": "planstatus.deposit",
    "בהליך אישור": "planstatus.inproc",
    "הכרעה בהתנגדויות / אישור": "planstatus.decision",
}


PERMIT_STATUS_KEYS = {
    "הופק-הוצא היתר בניה": "permitstatus.00",
    "הוכנה טיוטת היתר בניה": "permitstatus.01",
    "הבקשה נסגרה": "permitstatus.02",
    "נדונה בוועדת המשנה": "permitstatus.03",
    "התקבל תיק ורוד / מסמכים חתומים": "permitstatus.04",
    "שולמה מקדמה": "permitstatus.05",
    "נדונה ברשות הרישוי": "permitstatus.06",
    "נפתח תיק רישוי": "permitstatus.07",
    "הופק היתר מוארך": "permitstatus.08",
    "נדונה בועדת ערר": "permitstatus.09",
    "הגשה מקוונת הושלמה": "permitstatus.10",
    "ממתין לאישור נוסח פרסום": "permitstatus.11",
    'אושר ע"י מהנדס העיר': "permitstatus.12",
    "תום תקופת פרסום": "permitstatus.13",
    "חידוש טיפול בבקשה": "permitstatus.14",
    "התקבל ערר": "permitstatus.15",
    "הבקשה נגנזה": "permitstatus.16",
    "נוסח פרסום אושר": "permitstatus.17",
    "תחילת פרסום הבקשה להקלה": "permitstatus.18",
    "השלמת הודעות לפני תקנה 36": "permitstatus.19",
    "פורסמה בקשה להקלה": "permitstatus.20",
    "תחילת הודעות לפני תקנה 36": "permitstatus.21",
    "התקבלה בקשה לדיון המועצה": "permitstatus.22",
}


# Municipal permit-request type (sugbakasha) values with a translated label.
# The raw value stays in data-sug and in the filter's option value; only the
# shown text changes. A value not listed here is shown as the source gives it.
PERMIT_SUG_KEYS = {
    "תוספת בניה / הרחבה לבניין קיים": "permitsug.00",
    "תוספת בניה לדירות": "permitsug.01",
    "בניה חדשה / בניין חדש": "permitsug.02",
    "שינויים בבנין קיים": "permitsug.03",
    "בניית מרפסת": "permitsug.04",
    "תוכנית שינויים": "permitsug.05",
    "התקנת מעלית": "permitsug.06",
    "סגירת מרפסת": "permitsug.07",
    "חידוש היתר": "permitsug.08",
    "רישוי עסקים - שימוש חורג מתוכנית": "permitsug.09",
    "התקנת מתקנים מיוחדים": "permitsug.10",
    "רישוי בניה - שימוש חורג מהיתר": "permitsug.11",
    "בנית מחסן/מחסנים": "permitsug.12",
    "פרגולה": "permitsug.13",
    "תוספת מבנה-מגרש בנוי": "permitsug.14",
    "בניית גדר גבוהה מ 1.5 מטר": "permitsug.15",
    'תמ"א 38 - תוספות': "permitsug.16",
    "סגירת חורף": "permitsug.17",
    "שינויים בקירות חזית במבנים קיימים": "permitsug.18",
    "עבודות בקיר חיצון": "permitsug.19",
    "שנוי יעוד המבנה": "permitsug.20",
    'ממ"ד': "permitsug.21",
    "הכשרת שטח לחניה": "permitsug.22",
    "תכנית שינויים בסמכות מהנדס העיר": "permitsug.23",
    "מתקן שידור / אנטנה סלולרית": "permitsug.24",
    "התקנת גג רעפים": "permitsug.25",
    "פיתוח חצר": "permitsug.26",
    "חפירה ומילוי": "permitsug.27",
    "מדרגות": "permitsug.28",
    "ביצוע שיפור הנגישות לבניין ובתוכו": "permitsug.29",
    'תוספת יח"ד באמצעות תוספת בניה': "permitsug.30",
    "עבודות הריסה": "permitsug.31",
    "שינוי שם בהיתר": "permitsug.32",
    "עבודות בדרכים": "permitsug.33",
    "פיצול היתר": "permitsug.34",
    "התקנת חלון": "permitsug.35",
    "ריצוף חצר": "permitsug.36",
    "גג רעפים": "permitsug.37",
    "עבודות עפר": "permitsug.38",
    "שינויים ללא תוספת שטחים": "permitsug.39",
    "מערכת פוטוולטאית": "permitsug.40",
    'מבנה ארעי / מנ"ד': "permitsug.41",
    "התקנת צובר גז עד 10 טון": "permitsug.42",
    "פתיחת חלון": "permitsug.43",
    'תמ"א 38 הריסה ובניה': "permitsug.44",
    "התקנת צובר גז במשקל העולה על 10 טון": "permitsug.45",
    "הכשרת שטח לגן ציבורי": "permitsug.46",
    "עבודות סלילה": "permitsug.47",
    "יציקת תקרה": "permitsug.48",
    "בנית קירות פנימיים": "permitsug.49",
    "התקנת אביזרים": "permitsug.50",
    "הקמת סככה": "permitsug.51",
    "בניית קיר תומך/מגן": "permitsug.52",
    "בניית חניון": "permitsug.53",
    'פיצול יח"ד קיימות - צו שעה': "permitsug.54",
    "שיפורים סניטריים": "permitsug.55",
    "חדר טרנספורמציה": "permitsug.56",
    "הסרת סכנה לפי צו מבנים מסוכנים": "permitsug.57",
    "ריצוף רחוב": "permitsug.58",
    "בניית בריכה פרטית": "permitsug.59",
    "הצבת ביתן": "permitsug.60",
    "גשר כניסה לבנין": "permitsug.61",
    "פיתוח שטח ציבורי פתוח": "permitsug.62",
    "בית עלמין ללא תכנית שטחים": "permitsug.63",
    "ביטול היתר": "permitsug.64",
    "הצבת אנדרטה": "permitsug.65",
    "הכשרת מגרשי ספורט": "permitsug.66",
    "מחסן טרומי פריק": "permitsug.67",
    "סגירת בקשה להיתר": "permitsug.68",
    "רישוי בניה - שימוש חורג מתכנית": "permitsug.69",
    "גדר בגובה עד 1.50 מטר": "permitsug.70",
    "רישוי עסקים - שימוש חורג מהיתר": "permitsug.71",
}


def plan_status_label(lang: str, status: str) -> str:
    """Display text for a municipal plan status in lang (raw when unknown)."""
    key = PLAN_STATUS_KEYS.get(status)
    return t(lang, key) if key else status


def permit_status_label(lang: str, status: str) -> str:
    """Display text for a municipal permit-request status in lang (raw when
    the status has no translation)."""
    key = PERMIT_STATUS_KEYS.get(status)
    return t(lang, key) if key else status


def permit_sug_label(lang: str, sug: str) -> str:
    """Display text for a permit-request type in lang (raw when unknown)."""
    key = PERMIT_SUG_KEYS.get(sug)
    return t(lang, key) if key else sug
