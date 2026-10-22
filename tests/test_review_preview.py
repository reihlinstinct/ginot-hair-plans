from PIL import Image

from ginot import page, preview


def test_review_card_uses_public_fields_no_derived_deadline(tmp_path):
    row = {"pl_number": "101-1158146", "pl_name": "בית הנוער העברי",
           "station_desc": "במילוי תנאים להפקדה",
           "objection_deadline_derived_60d_from_publication": "2026-11-07"}
    image = tmp_path / "card.png"
    assert preview.render_review_preview(row, "2026-10-22", image)
    assert Image.open(image).size == (1200, 630)
    text = page.review_social_meta(row["pl_number"], '<unsafe "name">',
                                  "https://reihlinstinct.github.io/ginot-hair-plans/", True)
    assert "2026-11-07" not in text
    assert "&lt;unsafe &quot;" in text
    assert 'content="https://reihlinstinct.github.io/ginot-hair-plans/reviews/og_101-1158146.png"' in text
    assert 'content="https://reihlinstinct.github.io/ginot-hair-plans/reviews/talking_points_101-1158146.html"' in text
    assert 'name="twitter:card" content="summary_large_image"' in text


def test_fallback_image_and_no_base_url():
    text = page.review_social_meta("101-1", "test", "https://example.invalid/subpath/", False)
    assert 'content="https://example.invalid/subpath/og.png"' in text
    assert "og:image" not in page.review_social_meta("101-1", "test", "", False)


def test_existing_render_step_builds_review_metadata_and_image(tmp_path):
    plans = tmp_path / "plans" / "101-1" / "analysis"
    plans.mkdir(parents=True)
    (plans / "talking_points_101-1.md").write_text("# Test review", encoding="utf-8")
    output = tmp_path / "docs"
    page.render_site([{"pl_number": "101-1", "pl_name": "תכנית א", "station_desc": "אישור", "mavat_url": "https://example.invalid/plan",
                       "inside_flag": "inside", "pl_area_dunam": 1,
                       "objection_deadline_derived_60d_from_publication": "",
                       "receiving_date": "", "pl_last_deposit_date": "", "depositing_date": ""}],
                     [], str(output), base_url="https://example.invalid/subpath/",
                     plans_dir=str(tmp_path / "plans"))
    review = (output / "reviews/talking_points_101-1.html").read_text()
    assert 'property="og:title"' in review
    assert 'name="twitter:description"' in review
    assert Image.open(output / "reviews/og_101-1.png").size == (1200, 630)
    index = (output / "index.html").read_text()
    assert 'name="twitter:title"' in index
    assert 'name="twitter:description"' in index


def test_review_image_without_bidi_uses_default(tmp_path, monkeypatch):
    from PIL import features
    monkeypatch.setattr(features, "check", lambda key: False)
    assert not preview.render_review_preview({"pl_number": "101-1"}, "2026-10-22", tmp_path / "x.png")
