"""Format checks for the unverified-capabilities registry (issue #680)."""

import pathlib
import re

REGISTRY = pathlib.Path(__file__).parent.parent / "docs" / "operations" / "unverified-capabilities.md"
STATUS = re.compile(r"^(unverified|partial)\b")
DATE_OR_NEVER = re.compile(r"^(never|\d{4}-\d{2}-\d{2})\b")


def section_rows(heading: str):
    text = REGISTRY.read_text(encoding="utf-8")
    body = text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]
    rows = [ln for ln in body.splitlines() if ln.startswith("|")]
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in rows[2:]]


def test_unverified_rows_are_complete():
    rows = section_rows("Unverified")
    assert rows, "registry has no unverified rows"
    for cells in rows:
        assert len(cells) == 5, cells
        ident, claim, status, command, checked = cells
        assert re.fullmatch(r"U-\d{3}", ident), ident
        assert claim
        assert STATUS.match(status), f"{ident}: status must start with unverified or partial"
        assert "`" in command and "Pass" in command, f"{ident}: needs a command and a pass condition"
        assert DATE_OR_NEVER.match(checked), f"{ident}: last checked must be a date or never"


def test_verified_rows_have_evidence_and_date():
    for cells in section_rows("Verified"):
        assert len(cells) == 4, cells
        ident, claim, evidence, date = cells
        assert re.fullmatch(r"V-\d{3}", ident), ident
        assert claim and evidence
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), ident


def test_ids_are_unique():
    ids = [c[0] for h in ("Unverified", "Verified") for c in section_rows(h)]
    assert len(ids) == len(set(ids))
