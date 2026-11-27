"""Conflicting source dates stay raw, visible and unusable as deadlines."""

import copy
import json
import subprocess
from html import escape
from pathlib import Path

import pytest

from ginot import i18n
from ginot.page_permits import _permits_section


@pytest.mark.parametrize("lang", i18n.lang_codes())
def test_source_dates_preserved_and_warning_localized(lang, tmp_path):
    row = {
        "tik_num": "1969/0907.02",
        "status": "נוסח פרסום אושר",
        "publication_start": "2026-12-07",
        "publication_end_planned": "2026-12-03",
    }
    original = copy.deepcopy(row)
    full, default = tmp_path / "full.html", tmp_path / "default.html"
    html = _permits_section([row], str(full), str(default), lang=lang)
    for rendered in (html, full.read_text(), default.read_text()):
        assert "data-publication-chronology-warning" in rendered
        assert escape(i18n.t(lang, "permits.chronology_warning")) in rendered
        assert "07.12.26" in rendered and "03.12.26" in rendered
        assert "data-pub='2026-12-07'" in rendered
        assert "data-pubend='2026-12-03'" in rendered
    assert row == original


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-12-03", "2026-12-07"),
        ("2026-12-03", "2026-12-03"),
        ("", "2026-12-03"),
        ("2026-12-07", ""),
        ("2026-02-30", "2026-02-01"),
        ("2026-12-07", "2026-02-30"),
    ],
)
def test_warning_only_for_valid_inverted_date_pair(start, end):
    html = _permits_section(
        [{"publication_start": start, "publication_end_planned": end}]
    )
    assert "data-publication-chronology-warning" not in html


def test_conflict_cannot_hide_row_or_create_urgency_but_official_date_wins():
    source = (Path(__file__).resolve().parents[1] / "src/ginot/page.py").read_text()
    urgency = source.split("    var planned=r.getAttribute('data-pubend');", 1)[
        1
    ].split("    var parsed=Date.parse", 1)[0]
    window = source.split(
        "    var officialEnd=r.getAttribute('data-pubend-official')||'';", 1
    )[1].split("    var evidence=", 1)[0]
    js = (
        """
function validIso(s){return /^\\d{4}-\\d{2}-\\d{2}$/.test(s||'')&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;}
const validDeadline=validIso;
function urgent(r,official){let planned=r.getAttribute('data-pubend');
"""
        + urgency
        + """return d;}
function openEnd(r){let officialEnd=r.getAttribute('data-pubend-official')||'';
"""
        + window
        + """return pe;}
const results=[];
for(const official of ['', '2026-12-02']){
 let r={getAttribute(k){return {'data-pub':'2026-12-07','data-pubend':'2026-12-03','data-pubend-official':official}[k];}};
 results.push([urgent(r,official)||'',openEnd(r)]);
}
console.log(JSON.stringify(results));"""
    )
    p = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(p.stdout) == [["", ""], ["2026-12-02", "2026-12-02"]]
