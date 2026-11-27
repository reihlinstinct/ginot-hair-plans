"""Forum summaries on plan pages: explicit-number matches only, redacted hosted copies, visible table links."""

import json
from pathlib import Path

from ginot.page import _community_source_link
from ginot.page_permit_policy import COMMUNITY_SOURCE_RECORDS

ROOT = Path(__file__).resolve().parents[1]
NEW = [
    r
    for r in COMMUNITY_SOURCE_RECORDS
    if r[2] not in {"14.10.26", "04.11.26", "18.11.26"}
]


def test_every_record_has_redacted_copy_readme_and_note():
    assert len(NEW) == 19
    for cases, url, _date in NEW:
        pdf = ROOT / "docs" / url
        assert pdf.stat().st_size > 50000
        assert (pdf.parent / "README.md").exists()
        slug = pdf.parent.name.removeprefix("forum-").removesuffix("-source")
        for plan in cases:
            note = (ROOT / f"plans/{plan}/documents/forum-{slug}.md").read_text()
            assert url.rsplit("/", 1)[0] in note
            assert "הוסרו פרטי השתתפות" in note
            assert "אינו הוכחה להגשה בפועל" in note
            assert "איליאס" not in note


def test_links_only_on_listed_plans():
    assert "forum-2026-09-09-source" in _community_source_link("101-1404177")
    assert "forum-2024-03-06-source" in _community_source_link("101-1024645")
    assert "forum-2026-08-26" not in _community_source_link("101-1185578")
    assert _community_source_link("101-1185578") == ""


def test_live_rows_show_the_links():
    rows = (ROOT / "docs/rows.html").read_text()
    live = {
        r["pl_number"]
        for r in json.loads((ROOT / "docs/data.json").read_text())["rows"]
    }
    for cases, url, _d in NEW:
        for plan in cases & live:
            row = rows.split(f"data-num='{plan}'", 1)[1].split("</tr>", 1)[0]
            assert url in row
