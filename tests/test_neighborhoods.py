"""Neighborhood search index: data/neighborhoods.json + ginot.neighborhoods.

The free-text search must resolve a neighborhood name (and its spelling
variants) to the plans on its streets, without a new filter field.
"""

import json
from pathlib import Path

import pytest

from ginot import neighborhoods, page

ROOT = Path(__file__).parent.parent


# Section: matching


def test_mapu_plan_is_rehavia():
    # The plan from the user's photo: no neighborhood word in the name.
    assert neighborhoods.tags_for("הריסה ובניה בבנין ברח' מאפו 6, ירושלים") == ["רחביה"]


def test_anchored_streets_match_their_neighborhood():
    assert "רחביה" in neighborhoods.tags_for("תוספת קומה ברח' האר\"י 4, ירושלים")
    assert "קטמון" in neighborhoods.tags_for("שינוי הוראות ברח' מכור 7, י-ם")
    assert "טלביה" in neighborhoods.tags_for('הרחבת יח"ד ברחוב דוד מרכוס 11')


def test_sub_area_carries_the_parent_neighborhood():
    tags = neighborhoods.tags_for("הרחבות דיור ברח' בילו 1, קטמון הישנה")
    assert "קטמון הישנה" in tags and "קטמון" in tags


def test_lincoln_street_is_talbiya():
    # Lincoln 13's plan name has no neighborhood word (user report 18.11.2026).
    assert "טלביה" in neighborhoods.tags_for("התחדשות עירונית - לינקולן 13")


def test_variants_are_searchable():
    tags = neighborhoods.tags_for("תוספת שטחים בחובבי ציון 5")
    assert "טלביא" in tags  # the spelling variant is appended, not required


def test_whole_words_only():
    # מכוור (Katamonim/Gonenim) must not match the Katamon street מכור.
    assert neighborhoods.tags_for("וב מכוור בשכ' גוננים") == []


def test_prefix_rule_is_limited_to_multi_word_streets():
    # #998: למכור ("to sell") must not match the single-word street מכור;
    # the inseparable-preposition prefix applies to multi-word streets only.
    assert neighborhoods.tags_for("למכור ברח' הגפן 3") == []
    assert neighborhoods.tags_for("תוספת קומה במכור 7, י-ם") == []
    assert "טלביה" in neighborhoods.tags_for("תוספת שטחים בחובבי ציון 5")


# Section: full street-prefix regression matrix (#1011, follows #998)

_MULTI = "חובבי ציון"  # known multi-word street (טלביה)
_SINGLE = "מכור"  # known one-word street; must stay exact-match only


@pytest.mark.parametrize("prefix", list(neighborhoods._PREFIXES))
def test_every_prefix_matches_a_multi_word_street(prefix):
    assert "טלביה" in neighborhoods.tags_for(f"תוספת שטחים {prefix}{_MULTI} 5")


def test_unprefixed_multi_word_street_matches():
    assert "טלביה" in neighborhoods.tags_for(f"תוספת שטחים {_MULTI} 5")


@pytest.mark.parametrize("prefix", list(neighborhoods._PREFIXES))
def test_prefix_never_matches_a_single_word_street(prefix):
    assert neighborhoods.tags_for(f"תוספת קומה {prefix}{_SINGLE} 7") == []


def test_unprefixed_single_word_street_still_matches():
    assert neighborhoods.tags_for(f"תוספת קומה {_SINGLE} 7") != []


@pytest.mark.parametrize("prefix", ["וב", "בכ", "מש", "לב", "שה"])
def test_double_prefix_does_not_match(prefix):
    assert neighborhoods.tags_for(f"תוספת שטחים {prefix}{_MULTI} 5") == []


@pytest.mark.parametrize(
    "text",
    [
        "תוספת שטחים חובבי ציונים 5",  # suffix lookalike
        "תוספת שטחים בחובבי ציוןx 5",
        "תוספת שטחים חובבי איציון 5",  # embedded-word lookalike
        "תוספת שטחים בחובבי חובבי ציון5",
    ],
)
def test_suffix_and_embedded_lookalikes_do_not_match(text):
    assert neighborhoods.tags_for(text) == []


@pytest.mark.parametrize("letter", ["א", "ג", "ר", "נ", "ה", "ו"])
def test_unrelated_first_letter_is_rejected(letter):
    assert neighborhoods.tags_for(f"תוספת שטחים {letter}{_MULTI} 5") == []


def test_shared_street_is_excluded():
    # הפלמ"ח is anchored to three neighborhoods; it maps to none.
    assert neighborhoods.tags_for("בניין מגורים ברח' הפלמ\"ח 24") == []


def test_spelling_folding_matches_the_site():
    # Geresh/gershayim and maqaf fold exactly like the site's normSearch.
    assert "רחביה" in neighborhoods.tags_for("ברחוב רשב״א 10")
    assert "קטמון" in neighborhoods.tags_for("סן־מרטין 28")


def test_unknown_name_has_no_tags():
    assert neighborhoods.tags_for("רכבת קלה בירושלים - קו ירוק") == []


# Section: data file integrity


def test_data_file_covers_the_requested_neighborhoods():
    data = json.loads((ROOT / "data/neighborhoods.json").read_text(encoding="utf-8"))
    for name in ("רחביה", "קטמון", "טלביה", "קרית שמואל"):
        assert name in data["neighborhoods"]
    assert "קריית שמואל" in data["neighborhoods"]["קרית שמואל"]["variants"]
    assert data["neighborhoods"]["קטמון הישנה"]["parent"] == "קטמון"


def test_no_street_is_mapped_to_two_neighborhoods():
    data = json.loads((ROOT / "data/neighborhoods.json").read_text(encoding="utf-8"))
    seen = {}
    for name, entry in data["neighborhoods"].items():
        for street in entry.get("streets", {}):
            assert street not in seen, f"{street} in both {seen.get(street)} and {name}"
            seen[street] = name


# Section: page integration


def _plan_row(n, name, status="הפקדה"):
    return {
        "pl_number": str(n),
        "pl_name": name,
        "station_desc": status,
        "receiving_date": "2026-10-01",
        "pl_last_deposit_date": "",
        "depositing_date": "",
        "objection_deadline_derived_2m_from_publication": "",
        "pl_area_dunam": 1.0,
        "inside_flag": "inside",
        "mavat_url": "https://mavat.iplan.gov.il/x",
    }


def test_rows_carry_neighborhood_in_data_search(tmp_path):
    rows = [_plan_row("1", "הריסה ובניה ברח' מאפו 6, ירושלים")]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    rows_html = (tmp_path / "rows.html").read_text(encoding="utf-8")
    assert "data-search='1 הריסה ובניה ברח&#x27; מאפו 6, ירושלים רחביה'" in rows_html
    assert "רחביה" in html  # datalist term


def test_search_datalist_terms(tmp_path):
    rows = [_plan_row("101-1234567", "תכנית לדוגמה")]
    page.render_site(rows, [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<datalist id="fq-suggest">' in html
    for term in ("רחביה", "קטמון הישנה", "קריית שמואל", "מאפו", "101-1234567"):
        assert f"<option value='{term}'></option>" in html
    assert 'list="fq-suggest"' in html


def test_nonempty_search_overrides_approved_hiding(tmp_path):
    # The JS gate: approved rows stay hidden only while the query is empty.
    page.render_site([_plan_row("1", "תכנית", status="אישור")], [], str(tmp_path))
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "data-active')!=='1'&&!normSearch(fq.value)" in html
