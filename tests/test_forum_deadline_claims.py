"""Forum-summary deadline claims are attributed display context only."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ginot import page, refresh


def _write(tmp_path, plans):
    p = tmp_path / "claims.json"
    p.write_text(json.dumps({"plans": plans}), encoding="utf-8")
    return str(p)


def test_claim_attached_only_when_it_differs(tmp_path):
    path = _write(
        tmp_path,
        {
            "A": {"deadline": "2026-12-04", "forum_date": "2026-11-18", "source": "u"},
            "B": {"deadline": "2026-12-09", "forum_date": "2026-11-18", "source": "u"},
        },
    )
    rows = [
        {
            "pl_number": "A",
            "objection_deadline_derived_2m_from_publication": "2026-12-16",
        },
        {
            "pl_number": "B",
            "objection_deadline_derived_2m_from_publication": "2026-12-09",
        },
        {
            "pl_number": "C",
            "objection_deadline_derived_2m_from_publication": "2026-12-01",
        },
    ]
    out = refresh.merge_forum_deadline_claims(rows, path)
    assert out[0]["forum_deadline_claim"] == "2026-12-04"
    assert out[0]["forum_deadline_claim_source"] == "u"
    assert "forum_deadline_claim" not in out[1]
    assert "forum_deadline_claim" not in out[2]
    # the displayed/sorted deadline is untouched
    assert page._objection_deadline_iso(out[0]) == "2026-12-16"


def test_missing_file_is_a_noop(tmp_path):
    rows = [{"pl_number": "A"}]
    assert (
        refresh.merge_forum_deadline_claims(rows, str(tmp_path / "nope.json")) == rows
    )


def test_note_rendered_beside_computed_deadline():
    r = {
        "objection_deadline_derived_2m_from_publication": "2026-12-16",
        "forum_deadline_claim": "2026-12-04",
    }
    html = page._objection_cell(r, "", "CLAIM")
    assert "2026-12-16" in html and "CLAIM" in html and "forum-claim" in html
    assert "CLAIM" not in page._objection_cell(
        {"objection_deadline_derived_2m_from_publication": "2026-12-16"}, "", "CLAIM"
    )


def _stale_row(pl, derived):
    return {
        "pl_number": pl,
        "objection_deadline_derived_2m_from_publication": derived,
        "forum_deadline_claim": "2026-12-04",
        "forum_deadline_claim_forum_date": "2026-11-18",
        "forum_deadline_claim_source": "u",
    }


def test_stale_claim_cleared_when_computed_date_now_equals_claim(tmp_path):
    path = _write(
        tmp_path, {"A": {"deadline": "2026-12-04", "forum_date": "x", "source": "u"}}
    )
    out = refresh.merge_forum_deadline_claims([_stale_row("A", "2026-12-04")], path)
    assert not any(k.startswith("forum_deadline_claim") for k in out[0])


def test_stale_claim_cleared_when_entry_removed(tmp_path):
    path = _write(tmp_path, {})
    out = refresh.merge_forum_deadline_claims([_stale_row("A", "2026-12-16")], path)
    assert not any(k.startswith("forum_deadline_claim") for k in out[0])
    out = refresh.merge_forum_deadline_claims(
        [_stale_row("A", "2026-12-16")], str(tmp_path / "nope.json")
    )
    assert not any(k.startswith("forum_deadline_claim") for k in out[0])


def test_source_link_only_for_the_forum_site():
    base = {
        "objection_deadline_derived_2m_from_publication": "2026-12-16",
        "forum_deadline_claim": "2026-12-04",
    }
    ok = dict(
        base,
        forum_deadline_claim_source="https://www.ginothair.org.il/files/a b.pdf",
    )
    html = page._objection_cell(ok, "", "CLAIM")
    assert "<a href='https://www.ginothair.org.il/files/a b.pdf'" in html
    assert "noopener" in html and "2026-12-16" in html
    for bad in (
        "javascript:alert(1)",
        "http://www.ginothair.org.il/x",
        "https://evil.example/x",
    ):
        html = page._objection_cell(
            dict(base, forum_deadline_claim_source=bad), "", "CLAIM"
        )
        assert "<a " not in html.split("forum-claim")[1] and "CLAIM" in html
