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


def t(lang: str, key: str, **fmt) -> str:
    """The string for key in lang; falls back to the default language when
    that language has no entry. An unknown key is a programming error."""
    entry = load()["strings"][key]
    text = entry.get(lang) or entry[default_lang()]
    return text.format(**fmt) if fmt else text


def asset_prefix(lang: str) -> str:
    """Relative prefix from a page of lang back to the site root."""
    return "" if lang == default_lang() else "../"


def page_path(lang: str, name: str) -> str:
    """Path of page name for lang, from the site root (default at the root)."""
    return name if lang == default_lang() else f"{lang}/{name}"


def switcher(lang: str, name: str) -> str:
    """The language selector for page name, rendered from the document."""
    items = []
    for code in lang_codes():
        m = meta(code)
        href = asset_prefix(lang) + page_path(code, name)
        current = ' aria-current="true"' if code == lang else ""
        items.append(
            f'<a href="{escape(href)}" hreflang="{escape(m["lang"])}" '
            f'lang="{escape(m["lang"])}"{current}>{escape(m["name"])}</a>'
        )
    label = escape(t(lang, "ui.language"))
    return (
        f'<nav class="lang-switch" aria-label="{label}">'
        + " &middot; ".join(items)
        + "</nav>"
    )
