"""#825: forum material separates confirmed scopes from missing evidence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_inbal_review_has_scoped_claims_and_deadline_conflict():
    text = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text(encoding="utf-8")
    assert "29.11.2026" in text and "08.12.2026" in text
    assert "09.10.2026" in text and "לא אישור רשמי" in text
    assert "לא הוכחה פלישה למדרכה" in text
    assert "101-0193193" in text and "193103" in text
    assert "לא אומתה תוספת קומות" in text
    assert "פעילות הטופס וקבלתו לתכנית זו לא נבדקו" in text
    assert "מעריב הבוקר" in text and "שלומציון המלכה 1" in text
    assert "הודעה המאוחרת" in text
    assert "citybuildingplan/" in text
    assert "אין סיבה לתכנית זו להגיע" not in text


def test_forum_landing_has_all_cases_and_explicit_unresolved_identity():
    text = (ROOT / "docs/reviews/forum-2026-11-04.html").read_text(encoding="utf-8")
    assert 'lang="he" dir="rtl"' in text
    for anchor in ("p41", "p29", "inbal"):
        assert f'id="{anchor}"' in text
        assert f'href="#{anchor}"' in text
    assert "13.11.2026" in text and "17.11.2026" in text
    assert "זיהוי התיק עדיין בבירור" in text
    assert "לא הוגש דבר" in text
    assert "אפשרות לבירור, לא זיהוי מאושר" in text
    assert "101-1377753" in text
    assert "אינו מוכיח תקלה בסינון האתר" in text


def test_forum_local_links_resolve():
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.links += [v for k, v in attrs if k == "href"]

    folder = ROOT / "docs/reviews"
    for page in (
        "forum-2026-11-04.html",
        "talking_points_101-1488261.html",
        "palmach41/focused-2026-11-04.html",
    ):
        parser = Links()
        parser.feed((folder / page).read_text(encoding="utf-8"))
        for href in parser.links:
            if href.startswith(("http:", "https:", "#", "mailto:")):
                continue
            assert (
                (folder / page).parent.joinpath(href.split("#")[0]).resolve().is_file()
            ), href


def test_masterplan_comparison_marks_departures_and_limits():
    landing = (ROOT / "docs/reviews/forum-2026-11-04.html").read_text(encoding="utf-8")
    inbal = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text(encoding="utf-8")
    for text in (landing, inbal):
        assert "talbiye%20d1.pdf#page=24" in text
        assert "לא הוכחה חריגה מספרית" in text
        assert "hanchayot.pdf#page=53" in text
        assert "hanchayot.pdf#page=50" in text
    assert "פער של 2-3 קומות" in landing
    assert "אין עדיין בסיס לקביעת חריגה" in landing
    assert "מפלסים" in landing and "796.69" in landing
    assert "זהו חיפוש שם/מספר ולא בדיקת כתובת ממצה" in landing
    assert "גגות רעפים" in inbal


def test_plan_drawings_have_provenance_and_safe_assets():
    from PIL import Image

    landing = (ROOT / "docs/reviews/forum-2026-11-04.html").read_text(encoding="utf-8")
    inbal = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text(encoding="utf-8")
    assert "גיליון 22" in landing and "מסמך 24" in landing
    assert "גיליון 1 מתוך 1" in landing and "מונה תשריט 8" in inbal
    assert "הצבע הוורוד אינו מעטפת בניין מוצעת" in inbal
    assert "שטרם נקרא" in inbal and "אין למדוד" in inbal
    for name in ("palmach41-section22.png", "inbal-site.png", "inbal-south.png"):
        assert name in landing
        image = Image.open(ROOT / "docs/reviews/forum-2026-11-04-assets" / name)
        assert image.width >= 1000
        assert not image.getexif()
        assert not any(
            key in image.info
            for key in ("exif", "icc_profile", "XML:com.adobe.xmp", "Comment")
        )
    assert "inbal-site.png" in inbal and "inbal-south.png" in inbal
    assert "max-width:100%;height:auto" in inbal


def test_refined_palmach_policy_review_keeps_scope_and_measurement_limits():
    folder = ROOT / "docs/reviews/palmach41"
    md = (folder / "focused-2026-11-04.md").read_text(encoding="utf-8")
    html = (folder / "focused-2026-11-04.html").read_text(encoding="utf-8")
    for text in (md, html):
        for page in (12, 13, 14, 25, 26, 27, 50, 51, 53):
            assert f"hanchayot.pdf#page={page}" in text
        assert "767.40" in text and "762.50" in text
        assert "26.19" in text and "31.09" in text
        assert "בבניינים קיימים" in text
        assert "אין לאחד מכנים שונים" in text
        assert "אינה עוצרת" in text
        assert "לא נוסח מאושר למשלוח" in text
        assert "13.11.2026" in text
        assert "אינם בהכרח 42 רכבים חדשים" in text
        assert "מנהל תקין" in text
        assert "palmach41-section22.png" in text
    assert 'lang="he" dir="rtl"' in html
    assert "focused-2026-11-04.html" in (
        ROOT / "docs/reviews/forum-2026-11-04.html"
    ).read_text(encoding="utf-8")


def test_refined_inbal_page_references_and_area_not_building_rights():
    md = (ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md").read_text(
        encoding="utf-8"
    )
    html = (ROOT / "docs/reviews/talking_points_101-1488261.html").read_text(
        encoding="utf-8"
    )
    for text in (md, html):
        for term in (
            "מפתח עמודים",
            "עמ' 6",
            "עמ' 9",
            "עמ' 10",
            "עמ' 12",
            "1977/0463.12",
            "טבלת שטחי ייעוד קרקע",
            "לא טבלת זכויות בנייה",
            "מנהל תקין",
            "אינה עוצרת כשלעצמה",
            "מסלול ערר",
            "101-0193193",
        ):
            assert term in text


def test_refined_palmach_html_contains_complete_markdown_body():
    import markdown

    folder = ROOT / "docs/reviews/palmach41"
    md = (folder / "focused-2026-11-04.md").read_text(encoding="utf-8")
    html = (folder / "focused-2026-11-04.html").read_text(encoding="utf-8")
    assert markdown.markdown(md, extensions=["sane_lists", "fenced_code"]) in html


def test_municipal_original_gaps_are_explicit_and_not_policy_page_claims():
    text = (ROOT / "docs/reviews/palmach41/focused-2026-11-04.md").read_text(
        encoding="utf-8"
    )
    for term in (
        "מקור משני",
        "לא נפתחו מחדש",
        "לא עמודים ולא מספרי גיליונות",
        "מסמך 11",
        "מסמך 12",
        "מסמך 24",
        "16E57A23-0D2B-464C-ACAD-30895F07B87D",
        "1B904968-6923-4446-9CFD-23FD04F1E91C",
        "5D3BD126-6D0F-42D0-80A8-F3D6B714DB2A",
        "חסימת 403",
    ):
        assert term in text


def test_professional_executive_summaries_precede_explanation_and_link_drawings():
    p41 = (ROOT / "docs/reviews/palmach41/focused-2026-11-04.md").read_text()
    inbal = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text()
    heading = "## תקציר מנהלים: בדיקות בתכניות למהנדס"
    assert p41.index(heading) < p41.index("**שורה תחתונה:")
    assert inbal.index(heading) < inbal.index("## המועד האחרון:")
    for term in (
        "#drawing-form22",
        "#drawing-survey",
        "#drawing-access",
        "#drawing-floor2",
        "טבלה 2.1.5",
        "793.59",
        "796.69",
        "3,425.36",
        '80 ס"מ',
    ):
        assert term in p41
    for term in (
        "#inbal-drawings",
        "#inbal-operation",
        "מונה 11",
        "עמ' 9, טבלה 3.2",
        "1977/0463.12",
    ):
        assert term in inbal


def test_executive_drawings_are_real_assets_and_schematics_are_labelled():
    from PIL import Image

    folder = ROOT / "docs/reviews/forum-2026-11-04-assets"
    p41 = (ROOT / "docs/reviews/palmach41/focused-2026-11-04.md").read_text()
    inbal = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text()
    for name in (
        "p41-survey.png",
        "p41-form22.png",
        "p41-ramp.png",
        "p41-apron.png",
        "p41-floor2.png",
        "p41-level-check.png",
        "p41-coverage-check.png",
        "inbal-operation-check.png",
    ):
        image = Image.open(folder / name)
        assert image.width >= 1000
        assert not image.getexif()
        assert not any(
            key in image.info
            for key in ("exif", "icc_profile", "XML:com.adobe.xmp", "Comment")
        )
        assert name in p41 + inbal
    assert "מספר גיליון לא זוהה" in p41
    assert "לא רוחב המדרכה" in p41
    assert "תרשים סכמטי" in p41 and "תרשים סכמטי" in inbal


def test_executive_internal_anchors_resolve_and_forum_link_is_current():
    from html.parser import HTMLParser

    class Anchors(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()
            self.links = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if "id" in values:
                self.ids.add(values["id"])
            if tag == "a" and values.get("href", "").startswith("#"):
                self.links.append(values["href"][1:])

    for name in (
        "palmach41/focused-2026-11-04.html",
        "talking_points_101-1488261.html",
    ):
        parser = Anchors()
        parser.feed((ROOT / "docs/reviews" / name).read_text())
        assert all(target in parser.ids for target in parser.links)
    text = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text()
    assert "20e85bf5be20cdc024adb954d065c02c6178dc86" not in text
    assert (
        "https://reihlinstinct.github.io/ginot-hair-plans/reviews/forum-2026-11-04.html"
        in text
    )


def test_government_source_links_use_https():
    import re
    from urllib.parse import urlsplit

    for name in (
        "docs/reviews/palmach41/focused-2026-11-04.md",
        "docs/reviews/palmach41/focused-2026-11-04.html",
        "plans/101-1488261/analysis/talking_points_101-1488261.md",
        "docs/reviews/talking_points_101-1488261.html",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        links = [urlsplit(url) for url in re.findall(r'https?://[^\s<>"()]+', text)]
        government = [url for url in links if url.hostname == "www.gov.il"]
        assert government
        assert all(url.scheme == "https" for url in government)


def test_executive_citations_and_inbal_existing_asphalt_are_consistent():
    for suffix in ("md", "html"):
        text = (ROOT / f"docs/reviews/palmach41/focused-2026-11-04.{suffix}").read_text(
            encoding="utf-8"
        )
        checklist = text.split("תכסית וחלחול:", 1)[1].split("לחשב כל מכנה", 1)[0]
        assert all(f"hanchayot.pdf#page={page}" in checklist for page in (25, 13, 14))
    for name in (
        "plans/101-1488261/analysis/talking_points_101-1488261.md",
        "docs/reviews/talking_points_101-1488261.html",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "תוספת פיזית של כ-120" not in text
        assert "שטח אספלט קיים של כ-120" in text
        assert "ללא הגדלת מכסת הבנייה" in text
        assert "הרחבת חדר האשפה אל שטח גישת המשאית הקיים" in text
        assert "ללא גאומטריה או מפלס מאומתים" in text
