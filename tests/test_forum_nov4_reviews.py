"""#825: forum material separates confirmed scopes from missing evidence."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_inbal_review_has_scoped_claims_and_deadline_conflict():
    text = (
        ROOT / "plans/101-1488261/analysis/talking_points_101-1488261.md"
    ).read_text(encoding="utf-8")
    assert "29.11.2026" in text and "08.12.2026" in text
    assert "09.10.2026" in text and "טרם אומת" in text
    assert "לא הוכחה פלישה למדרכה" in text
    assert "101-0193193" in text and "193103" in text
    assert "לא אומתה תוספת קומות" in text
    assert "לא אומת כאן מסלול מקוון ייעודי" in text
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
    for page in ("forum-2026-11-04.html", "talking_points_101-1488261.html"):
        parser = Links()
        parser.feed((folder / page).read_text(encoding="utf-8"))
        for href in parser.links:
            if href.startswith(("http:", "https:", "#", "mailto:")):
                continue
            assert (folder / href.split("#")[0]).resolve().is_file(), href
