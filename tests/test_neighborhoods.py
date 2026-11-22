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


# Section: sourced street aliases (#468)


def test_king_george_alias_finds_the_kings_hotel_plan():
    # The owner report: "קינג גורג" missed plan 101-0617134, officially
    # "מלון המלכים- המלך ג'ורג' 60". The sourced street_aliases entry
    # bridges the colloquial street name.
    extra = neighborhoods.search_extra("מלון המלכים- המלך ג'ורג' 60")
    assert "קינג גורג 60" in extra


def test_alias_variant_keeps_the_house_number():
    # The swap emits the whole name variant, so a query with the house
    # number still matches.
    extra = neighborhoods.search_extra("שיפוץ מבנה ברחוב המלך ג'ורג' 12, ירושלים")
    assert "קינג גורג 12" in extra


def test_alias_requires_the_whole_street_name():
    # Whole-word discipline: המלך alone or גורג alone must not trigger it.
    assert (
        neighborhoods._alias_variants(tuple(neighborhoods._norm("המלך דוד 5").split()))
        == []
    )
    assert (
        neighborhoods._alias_variants(
            tuple(neighborhoods._norm("גורג וושינגטון 3").split())
        )
        == []
    )


def test_alias_in_the_autocomplete_datalist():
    assert "קינג ג'ורג'" in neighborhoods.autocomplete_terms()


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


def test_shared_street_without_a_number_is_excluded():
    # הפלמ"ח spans several neighborhoods; without a house number the
    # plan's neighborhood is unknown (#998).
    assert neighborhoods.tags_for("שינוי הוראות ברח' הפלמ\"ח, ירושלים") == []


# Section: house-number ranges on a shared street (#998)


def test_palmach_even_low_numbers_are_kiryat_shmuel():
    # Parcel-level join against the JTMT neighborhood layer: even
    # 12-26 sit inside קריית שמואל.
    tags = neighborhoods.tags_for("בניין מגורים ברח' הפלמ\"ח 24, ירושלים")
    assert tags == ["קריית שמואל", "קרית שמואל"]


def test_palmach_odd_low_numbers_are_old_katamon():
    tags = neighborhoods.tags_for('הרחבת יח"ד ברח\' הפלמ"ח 25')
    assert "קטמון הישנה" in tags and "קטמון" in tags  # parent rides along
    assert "קרית שמואל" not in tags


def test_palmach_27_follows_the_municipality_plan_name():
    # The municipality's own plan name calls הפלמ"ח 27 קרית שמואל, so a
    # 27-27 range sits inside קטמון הישנה's wider odd range and the
    # narrowest range wins.
    tags = neighborhoods.tags_for('הרחבת יח"ד ברח\' הפלמ"ח 27, קרית שמואל, ירושלים.')
    assert tags == ["קריית שמואל", "קרית שמואל"]


def test_palmach_without_the_hay_prefix_still_matches():
    assert "קרית שמואל" in neighborhoods.tags_for('בניין מגורים ברחוב פלמ"ח 18')


def test_palmach_high_numbers_are_not_tagged():
    # 59+ is גבעת הורדים-רסקו per the GIS layer but קטמון per the
    # municipality's plan names: the sources disagree, so no tag yet.
    assert neighborhoods.tags_for("הריסה ובנייה ברח' הפלמ\"ח 66") == []
    assert neighborhoods.tags_for('בניין מגורים ברחוב פלמ"ח 48 ירושלים') == []


def test_palmach_multiple_numbers_tag_once():
    tags = neighborhoods.tags_for('התחדשות עירונית הפלמ"ח 49, 51 והשיירות 2')
    assert "קטמון הישנה" in tags


def test_palmach_number_outside_every_range_tags_nothing():
    # 2 is even: inside no anchored range (odd side is 1-51, even side
    # starts at 12), so nothing tags.
    assert neighborhoods.tags_for("תוספת קומה ברח' הפלמ\"ח 2א") == []


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
        for street, spec in entry.get("streets", {}).items():
            if street in seen:
                # A shared street is allowed only with house-number
                # ranges on every entry (#998), never as a plain anchor.
                assert isinstance(spec, dict) and spec.get("ranges"), street
                other = seen[street]
                assert isinstance(other[1], dict) and other[1].get("ranges"), street
                for a in other[1]["ranges"]:
                    for b in spec["ranges"]:
                        same_parity = {
                            a.get("parity", "any"),
                            b.get("parity", "any"),
                        } != {
                            "odd",
                            "even",
                        }
                        overlap = a["from"] <= b["to"] and b["from"] <= a["to"]
                        if same_parity and overlap:
                            # Allowed only as an explicit exception island
                            # (narrowest range wins): one range strictly
                            # inside the other, never identical spans.
                            nested = (
                                a["from"] >= b["from"] and a["to"] <= b["to"]
                            ) or (b["from"] >= a["from"] and b["to"] <= a["to"])
                            identical = a["from"] == b["from"] and a["to"] == b["to"]
                            assert nested and not identical, street
            else:
                seen[street] = (name, spec)


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


def test_kiryat_shmuel_unique_streets():
    # הרב חן (23/23) and חיים ברודי (19/19): every geolocated permit
    # parcel on these streets sits in קריית שמואל (#1006, JTMT join).
    assert "קרית שמואל" in neighborhoods.tags_for("תוספת יח\"ד ברח' הרב חן 4")
    assert "קרית שמואל" in neighborhoods.tags_for("שינוי הוראות בחיים ברודי 7")
