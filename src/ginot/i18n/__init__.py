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
