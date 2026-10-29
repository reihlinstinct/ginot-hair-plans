"""Regression tests for #405: the permit feed's data update must rebuild
docs/permits.html in the same run, so a newly published permit is visible
and searchable on the site immediately - not after the weekly refresh."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "render_permits_page.py"


def _run(cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, cwd=cwd, capture_output=True, text=True
    )


def test_newly_published_tik_renders_as_visible_searchable_row(tmp_path):
    """The user's 2026-10-24 repro: tik 2026/0439.00 (הפלמח 41, status
    תחילת פרסום הבקשה להקלה) was in data/permit_requests.json but missing
    from the deployed fragment. The renderer must emit it as an active row
    whose data-search matches the user's own searches."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    tik = {
        "tik_num": "2026/0439.00",
        "mahut": 'תכנית במתווה תמ"א 38 הריסה ובנייה מחדש.',
        "sugbakasha": 'תכנית במתווה תמ"א 38',
        "status": "תחילת פרסום הבקשה להקלה",
        "status_date": "2026-10-18",
        "gush": 30007,
        "helka": 12,
        "publication_start": "2026-10-18",
        "publication_end_planned": "2026-11-24",
        "address": "הפלמח 41 קטמון הישנה",
    }
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": [tik]}, ensure_ascii=False), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    fragment = (tmp_path / "docs" / "permits.html").read_text(encoding="utf-8")
    assert "2026/0439.00" in fragment
    assert "data-active='1'" in fragment  # not hidden as a terminal request
    assert "תחילת פרסום הבקשה להקלה" in fragment
    # the user's text searches all hit data-search (lowercased by the renderer)
    assert "הפלמח 41" in fragment
    assert "הפלמח 41" in fragment.split("data-search='", 1)[1].split("'", 1)[0]


def test_refuses_to_overwrite_with_empty_feed(tmp_path):
    """A broken/empty feed must fail red, never blank the live fragment."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": []}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode != 0
    assert not (tmp_path / "docs" / "permits.html").exists()


def test_permit_ids_published_for_submit_worker(tmp_path):
    """#515: the same run writes docs/permit-ids.json, the list the submit
    worker checks tik_num against. Sorted, de-duplicated, malformed ids dropped."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    rows = [
        {"tik_num": "2026/0439.00", "status": "תחילת פרסום הבקשה להקלה", "gush": 30007, "helka": 12},
        {"tik_num": "1981/0696.03", "status": "הבקשה נסגרה", "gush": 30007, "helka": 12},
        {"tik_num": "2026/0439.00", "status": "dup", "gush": 30007, "helka": 12},
        {"tik_num": "not-a-tik", "status": "x", "gush": 1, "helka": 1},
    ]
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": rows}, ensure_ascii=False), encoding="utf-8"
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    ids = json.loads((tmp_path / "docs" / "permit-ids.json").read_text(encoding="utf-8"))["ids"]
    assert ids == ["1981/0696.03", "2026/0439.00"]


def test_feed_publishes_parcel_points_and_labels_unmatched_rows(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'docs').mkdir()
    permits = [{'tik_num': '2026/0439.00', 'gush': 30007, 'helka': 12},
               {'tik_num': '2026/0001.00', 'gush': 1, 'helka': 1}]
    (tmp_path / 'data/permit_requests.json').write_text(json.dumps({'requests': permits}))
    (tmp_path / 'data/ginot_hair_parcels.geojson').write_text(json.dumps({'features': [{
        'properties': {'gush': 30007, 'helka': 12},
        'geometry': {'type': 'Polygon', 'coordinates': [[[35.21, 31.76], [35.22, 31.76],
                       [35.22, 31.77], [35.21, 31.77], [35.21, 31.76]]]}}]}))
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    points = json.loads((tmp_path / 'docs/permit-points.json').read_text())
    assert [p['tik_num'] for p in points['points']] == ['2026/0439.00']
    assert points['missing_location'] == ['2026/0001.00']
    fragment = (tmp_path / 'docs/permits.html').read_text()
    rows = fragment.split('<tr ')[1:]
    assert 'אין מיקום' not in rows[0]
    assert 'אין מיקום' in rows[1]


def test_permit_ai_review_column_links_published_review_and_labels_missing():
    from ginot.page import _permits_section

    html = _permits_section([{'tik_num': '2026/0439.00'}, {'tik_num': '2026/0001.00'}])
    assert '<th title="סיכום שהופק באמצעות AI - אינו מסמך רשמי">סקירת AI</th>' in html
    assert "href='reviews/palmach41/review-2026-0439.00.html'" in html
    assert 'טרם פורסמה סקירה' in html
    assert html.count('<td') == 18
    assert 'אינו מסמך רשמי' in html


def test_permit_ai_review_mobile_label_and_no_sort_button():
    from ginot.page import _CSS, _permits_section

    assert '#permits-table td:nth-child(9)::before{content:"סקירת AI"}' in _CSS
    header = _permits_section([{'tik_num': '2026/0439.00'}]).split('<thead>', 1)[1].split('</thead>', 1)[0]
    assert 'סקירת AI' in header
    assert '<button' not in header


def test_default_subset_rendered_with_full_fragment(tmp_path):
    """#441: the same batch writes docs/permits-default.html: active rows of a
    default-visible group, plus active rows with in-polygon publication
    evidence the #573 overlay may promote. Closed rows and evidence-less rows
    of a non-default group stay only in the full fragment."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    rows = [
        {"tik_num": "2026/0001.00", "status": "תחילת פרסום הבקשה להקלה", "gush": 1, "helka": 1},
        {"tik_num": "2026/0002.00", "status": "הבקשה נסגרה", "gush": 1, "helka": 1},
        {"tik_num": "2026/0003.00", "status": "נפתח תיק רישוי", "gush": 1, "helka": 1},
        {"tik_num": "2026/0004.00", "status": "נפתח תיק רישוי", "gush": 1, "helka": 1},
    ]
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": rows}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "data" / "publications_active.json").write_text(
        json.dumps([
            {"tik_num": "2026/0003.00", "in_polygon": True, "publication_date": "2026-10-01"},
            {"tik_num": "2026/0004.00", "in_polygon": None, "publication_date": "2026-10-01"},
        ]),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    full = (tmp_path / "docs" / "permits.html").read_text(encoding="utf-8")
    subset = (tmp_path / "docs" / "permits-default.html").read_text(encoding="utf-8")
    assert all(t["tik_num"] in full for t in rows)
    assert "2026/0001.00" in subset
    assert "2026/0003.00" in subset  # non-default group, in-polygon evidence
    assert "2026/0002.00" not in subset
    assert "2026/0004.00" not in subset
    # every subset row is byte-identical to its full-fragment row
    for line in subset.split("</tr>")[:-1]:
        assert line + "</tr>" in full
