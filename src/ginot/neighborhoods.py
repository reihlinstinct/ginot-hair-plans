"""Neighborhood search index (data/neighborhoods.json).

Appends neighborhood names and spelling variants to each plan row's
data-search text, so the existing free-text search resolves a
neighborhood name to the plans on its streets. Streets come from the
municipality's own plan names (source "plan-names") plus a short
hand-checked list ("manual"); streets anchored to more than one
neighborhood (הפלמ"ח) are excluded on purpose. Matching folds spelling
exactly like the site's normSearch (#413, #468) and compares whole
words only, so מכור never matches מכוור.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "neighborhoods.json"
)

# The same folding as the site's normSearch (page.py _NORM_SEARCH_JS):
# lowercase; drop niqqud/cantillation (incl. maqaf), geresh/gershayim,
# quotes/primes, hyphens/dashes and invisible bidi/zero-width marks;
# collapse whitespace.
_FOLD = re.compile("[֑-ׇ׳״´ʹʼ‐-―‘-‟′″−'\"`-]")
_INVISIBLE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2066-\u2069]"
)
_PREFIXES = "בכלמש"  # inseparable prepositions: בחובבי ציון = חובבי ציון


def _norm(text: str) -> str:
    """normSearch-equivalent folding for matching at build time."""
    text = _FOLD.sub("", (text or "").lower())
    text = _INVISIBLE.sub("", text)
    return " ".join(text.split())


@lru_cache(maxsize=1)
def _mapping() -> dict:
    """Street word-tuple -> set of neighborhood labels (incl. variants
    and the parent neighborhood of a sub-area)."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    neighborhoods = data["neighborhoods"]
    mapping: dict[tuple, set] = {}
    for name, entry in neighborhoods.items():
        labels = {name, *entry.get("variants", [])}
        parent = entry.get("parent")
        if parent:
            labels.add(parent)
            labels.update(neighborhoods[parent].get("variants", []))
        for street in entry.get("streets", {}):
            key = tuple(_norm(street).split())
            if key:
                mapping.setdefault(key, set()).update(labels)
    return mapping


def _first_word_matches(word: str, key_word: str) -> bool:
    """A word matches a street's first word exactly or with one
    inseparable preposition prefix (בחובבי ציון = חובבי ציון)."""
    return word == key_word or (
        len(word) == len(key_word) + 1 and word[0] in _PREFIXES and word[1:] == key_word
    )


def tags_for(plan_name: str) -> list[str]:
    """Neighborhood labels for a plan name, whole-word matches only."""
    words = tuple(_norm(plan_name).split())
    tags: set = set()
    for key, labels in _mapping().items():
        n = len(key)
        for i in range(len(words) - n + 1):
            if (
                _first_word_matches(words[i], key[0])
                and words[i + 1 : i + n] == key[1:]
            ):
                tags.update(labels)
                break
    return sorted(tags)


def search_extra(plan_name: str) -> str:
    """The text appended to a row's data-search (may be empty)."""
    return " ".join(tags_for(plan_name))


def autocomplete_terms() -> list[str]:
    """Neighborhoods, their variants and streets for the search datalist."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    terms = []
    for name, entry in data["neighborhoods"].items():
        terms.append(name)
        terms.extend(entry.get("variants", []))
        terms.extend(entry.get("streets", {}))
    return sorted(set(terms))
