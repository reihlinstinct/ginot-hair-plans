"""Neighborhood search index: data/neighborhoods.json + ginot.neighborhoods.

The free-text search must resolve a neighborhood name (and its spelling
variants) to the plans on its streets, without a new filter field.
"""

import json
from pathlib import Path

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
