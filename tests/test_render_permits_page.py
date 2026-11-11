"""Regression tests for #405: the permit feed's data update must rebuild
docs/permits.html in the same run, so a newly published permit is visible
and searchable on the site immediately - not after the weekly refresh."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "render_permits_page.py"


# Section: Offline render fixture


def _run(cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


# Section: Rendered data and atomic writes


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


def test_batch_updates_data_json_permits(tmp_path):
    """#559: docs/data.json is the public endpoint the MCP server serves;
    a permit-feed batch must refresh its permits[] in the same run, keeping
    generated/rows/changes (owned by the weekly refresh) untouched."""
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
    before = {
        "generated": "2026-10-01",
        "rows": [{"pl_number": "101-0000001"}],
        "changes": [],
        "permits": [{"tik_num": "1981/0696.03", "status": "הבקשה נסגרה"}],
    }
    (tmp_path / "docs" / "data.json").write_text(
        json.dumps(before, ensure_ascii=False), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    data = json.loads((tmp_path / "docs" / "data.json").read_text(encoding="utf-8"))
    assert [p["tik_num"] for p in data["permits"]] == ["2026/0439.00"]
    assert data["permits"][0]["status"] == "תחילת פרסום הבקשה להקלה"
    assert "_map_missing" in data["permits"][0]  # same annotation as the weekly build
    # weekly-owned keys are untouched
    assert data["generated"] == "2026-10-01"
    assert data["rows"] == [{"pl_number": "101-0000001"}]
    assert data["changes"] == []


def test_failed_write_leaves_original_and_no_temp_files(tmp_path, monkeypatch):
    """The atomic rewrite must never leave a truncated public endpoint or
    stray temp files when the dump itself blows up."""
    spec = importlib.util.spec_from_file_location("rpp", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "docs").mkdir()
    original = {"generated": "2026-10-01", "rows": [], "changes": [], "permits": []}
    (tmp_path / "docs" / "data.json").write_text(
        json.dumps(original, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.json, "dump", boom)
    try:
        module.update_data_json([{"tik_num": "2026/0439.00"}])
    except OSError:
        pass
    else:
        raise AssertionError("update_data_json swallowed the write failure")
    assert json.loads((tmp_path / "docs" / "data.json").read_text()) == original
    assert not list((tmp_path / "docs").glob(".data-*"))


def test_missing_data_json_is_left_to_the_weekly_refresh(tmp_path):
    """The batch never creates data.json from scratch: without the weekly
    keys there is nothing to keep, and a permits-only file would look like
    a complete dataset to the MCP server."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    tik = {"tik_num": "2026/0439.00", "status": "x", "gush": 30007, "helka": 12}
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": [tik]}, ensure_ascii=False), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "docs" / "data.json").exists()


def test_refuses_to_overwrite_with_empty_feed(tmp_path):
    """A broken/empty feed must fail red, never blank the live fragment."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": []}), encoding="utf-8"
    )
    result = _run(tmp_path)
    assert result.returncode != 0
    assert not (tmp_path / "docs" / "permits.html").exists()


# Section: Published identifiers and geometry


def test_permit_ids_published_for_submit_worker(tmp_path):
    """#515: the same run writes docs/permit-ids.json, the list the submit
    worker checks tik_num against. Sorted, de-duplicated, malformed ids dropped."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    rows = [
        {
            "tik_num": "2026/0439.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "gush": 30007,
            "helka": 12,
        },
        {
            "tik_num": "1981/0696.03",
            "status": "הבקשה נסגרה",
            "gush": 30007,
            "helka": 12,
        },
        {"tik_num": "2026/0439.00", "status": "dup", "gush": 30007, "helka": 12},
        {"tik_num": "not-a-tik", "status": "x", "gush": 1, "helka": 1},
    ]
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": rows}, ensure_ascii=False), encoding="utf-8"
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    ids = json.loads(
        (tmp_path / "docs" / "permit-ids.json").read_text(encoding="utf-8")
    )["ids"]
    assert ids == ["1981/0696.03", "2026/0439.00"]


def test_feed_publishes_parcel_points_and_labels_unmatched_rows(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    permits = [
        {"tik_num": "2026/0439.00", "gush": 30007, "helka": 12},
        {"tik_num": "2026/0001.00", "gush": 1, "helka": 1},
    ]
    (tmp_path / "data/permit_requests.json").write_text(
        json.dumps({"requests": permits})
    )
    (tmp_path / "data/ginot_hair_parcels.geojson").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "properties": {"gush": 30007, "helka": 12},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [35.21, 31.76],
                                    [35.22, 31.76],
                                    [35.22, 31.77],
                                    [35.21, 31.77],
                                    [35.21, 31.76],
                                ]
                            ],
                        },
                    }
                ]
            }
        )
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    points = json.loads((tmp_path / "docs/permit-points.json").read_text())
    assert [p["tik_num"] for p in points["points"]] == ["2026/0439.00"]
    assert points["missing_location"] == ["2026/0001.00"]
    fragment = (tmp_path / "docs/permits.html").read_text()
    rows = fragment.split("<tr ")[1:]
    assert "אין מיקום" not in rows[0]
    assert "אין מיקום" in rows[1]


def test_permit_ai_review_column_links_published_review_and_labels_missing():
    from ginot.page import _permits_section

    html = _permits_section([{"tik_num": "2026/0439.00"}, {"tik_num": "2026/0001.00"}])
    assert '<th title="סיכום שהופק באמצעות AI - אינו מסמך רשמי">סקירת AI</th>' in html
    assert "href='reviews/palmach41/review-2026-0439.00.html'" in html
    assert "טרם פורסמה סקירה" in html
    assert html.count("<td") == 18
    assert "אינו מסמך רשמי" in html


def test_permit_ai_review_mobile_label_and_no_sort_button():
    from ginot.page import _CSS, _permits_section

    # mobile row labels come from data-label attributes (i18n-aware), not CSS content
    assert "content:attr(data-label)" in _CSS
    section = _permits_section([{"tik_num": "2026/0439.00"}])
    header = section.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert "סקירת AI" in header
    assert "<button" not in header
    assert "data-label='סקירת AI'" in section


# Section: Default subset and privacy projection


def test_default_subset_rendered_with_full_fragment(tmp_path):
    """#441: the same batch writes docs/permits-default.html: active rows of a
    default-visible group, plus active rows with in-polygon publication
    evidence the #573 overlay may promote. Closed rows and evidence-less rows
    of a non-default group stay only in the full fragment."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    rows = [
        {
            "tik_num": "2026/0001.00",
            "status": "תחילת פרסום הבקשה להקלה",
            "gush": 1,
            "helka": 1,
        },
        {"tik_num": "2026/0002.00", "status": "הבקשה נסגרה", "gush": 1, "helka": 1},
        {"tik_num": "2026/0003.00", "status": "נפתח תיק רישוי", "gush": 1, "helka": 1},
        {"tik_num": "2026/0004.00", "status": "נפתח תיק רישוי", "gush": 1, "helka": 1},
    ]
    (tmp_path / "data" / "permit_requests.json").write_text(
        json.dumps({"requests": rows}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "data" / "publications_active.json").write_text(
        json.dumps(
            [
                {
                    "tik_num": "2026/0003.00",
                    "in_polygon": True,
                    "publication_date": "2026-10-01",
                },
                {
                    "tik_num": "2026/0004.00",
                    "in_polygon": None,
                    "publication_date": "2026-10-01",
                },
            ]
        ),
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


def test_batch_data_json_drops_unapproved_permit_fields(tmp_path):
    """#123: the feed writer must not bypass the weekly privacy projection."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs").mkdir()
    secret = "SYNTHETIC_PRIVATE_SENTINEL"
    permit = {
        "tik_num": "2026/0439.00",
        "status": "תחילת פרסום הבקשה להקלה",
        "gush": 30007,
        "helka": 12,
        "address": "רחוב לבדיקה 1",
        "baaleiInyanList": [secret],
        "planner_note": secret,
        "phone": secret,
        "national_id": secret,
        "future_private": secret,
        "details_checked_on": {"nested_private": secret},
    }
    (tmp_path / "data/permit_requests.json").write_text(
        json.dumps({"requests": [permit]}), encoding="utf-8"
    )
    before = {
        "generated": "2026-11-06",
        "rows": [{"pl_number": "101-1"}],
        "changes": [],
        "permits": [],
    }
    (tmp_path / "docs/data.json").write_text(json.dumps(before), encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "docs/data.json").read_text(encoding="utf-8")
    assert secret not in text
    data = json.loads(text)
    assert data["permits"][0]["tik_num"] == "2026/0439.00"
    assert data["permits"][0]["status"] == permit["status"]
    assert "details_checked_on" not in data["permits"][0]
    for key in ["generated", "rows", "changes"]:
        assert data[key] == before[key]
