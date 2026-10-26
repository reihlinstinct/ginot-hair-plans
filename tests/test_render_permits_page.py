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
