"""Neighborhood search index (data/neighborhoods.json).

Appends neighborhood names and spelling variants to each plan row's
data-search text, so the existing free-text search resolves a
neighborhood name to the plans on its streets. Streets come from the
municipality's own plan names (source "plan-names") plus a short
hand-checked list ("manual"). A street shared by several neighborhoods
is anchored with house-number ranges instead (source "manual+gis",
#998): הפלמ"ח splits odd 1-51 = קטמון הישנה, even 12-26 and 27 =
קרית שמואל, from a parcel-level join against the JTMT neighborhood
layer plus the municipality's plan-name anchors; numbers outside every
range tag nothing. Matching folds spelling exactly like the site's
normSearch (#413, #468) and compares whole words only, so מכור never
matches מכוור.
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
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
_PREFIXES = "בכלמש"  # inseparable prepositions: בחובבי ציון = חובבי ציון


def _norm(text: str) -> str:
    """normSearch-equivalent folding for matching at build time."""
    text = _FOLD.sub("", (text or "").lower())
    text = _INVISIBLE.sub("", text)
    return " ".join(text.split())


def _ranges(entry: dict) -> tuple | None:
    """House-number ranges of a street entry, or None when plain."""
    if not isinstance(entry, dict):
        return None
    return tuple((r["from"], r["to"], r.get("parity", "any")) for r in entry["ranges"])


@lru_cache(maxsize=1)
def _mapping() -> dict:
    """Street word-tuple -> list of (labels, ranges). Labels include
    variants and the parent neighborhood of a sub-area; ranges is None
    for a uniquely anchored street."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    neighborhoods = data["neighborhoods"]
    mapping: dict[tuple, list] = {}
    for name, entry in neighborhoods.items():
        labels = {name, *entry.get("variants", [])}
        parent = entry.get("parent")
        if parent:
            labels.add(parent)
            labels.update(neighborhoods[parent].get("variants", []))
        for street, spec in entry.get("streets", {}).items():
            key = tuple(_norm(street).split())
            if key:
                mapping.setdefault(key, []).append((frozenset(labels), _ranges(spec)))
    return mapping


def _first_word_matches(word: str, key_word: str, multi_word: bool) -> bool:
    """A word matches a street's first word exactly or - multi-word
    streets only - with one inseparable preposition prefix
    (בחובבי ציון = חובבי ציון). Single-word streets take the exact
    match alone: a prefix there false-positives on ordinary words
    (למכור must not match the street מכור, #998)."""
    return word == key_word or (
        multi_word
        and len(word) == len(key_word) + 1
        and word[0] in _PREFIXES
        and word[1:] == key_word
    )


_NUMBER = re.compile(r"^\d{1,3}")


def _house_numbers(words: tuple) -> list[int]:
    """Leading house numbers right after a matched street (24, 48א,
    49, 51 - commas are left by folding); stops at the first word that
    does not start with a digit."""
    numbers = []
    for word in words:
        m = _NUMBER.match(word)
        if not m:
            break
        numbers.append(int(m.group()))
    return numbers


def _in_ranges(number: int, ranges: tuple) -> bool:
    parity = "odd" if number % 2 else "even"
    return any(lo <= number <= hi and p in ("any", parity) for lo, hi, p in ranges)


def tags_for(plan_name: str) -> list[str]:
    """Neighborhood labels for a plan name, whole-word matches only."""
    words = tuple(_norm(plan_name).split())
    tags: set = set()
    ranged: set = set()  # (width, label) candidates from ranged streets
    for key, entries in _mapping().items():
        n = len(key)
        for i in range(len(words) - n + 1):
            if not (
                _first_word_matches(words[i], key[0], n > 1)
                and words[i + 1 : i + n] == key[1:]
            ):
                continue
            numbers = _house_numbers(words[i + n :])
            for labels, ranges in entries:
                if ranges is None:
                    tags.update(labels)
                else:
                    for number in numbers:
                        if _in_ranges(number, ranges):
                            width = min(
                                hi - lo
                                for lo, hi, p in ranges
                                if _in_ranges(number, ((lo, hi, p),))
                            )
                            ranged.update((width, label) for label in labels)
                            break
    if ranged:
        # Several neighborhoods can anchor the same street with
        # different ranges (קרית שמואל's 27-27 inside קטמון הישנה's
        # 1-51): the narrowest matching range wins. Equal-width claims
        # from different labels would all tag, but the data has none.
        best = min(width for width, _ in ranged)
        winners = {label for width, label in ranged if width == best}
        wider = {label for width, label in ranged if width > best}
        tags.update(winners - wider)
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
