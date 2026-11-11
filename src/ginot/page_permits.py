"""Server-rendered permit table and default subset fragments."""

import datetime

from .page_permit_policy import (
    _PERMIT_GROUP_CLASS,
    _PERMIT_PUB_EVIDENCE_STATUSES,
    _PERMIT_TERMINAL_STATUSES,
    PERMIT_STATUS_GROUPS,
    _is_default_permit_candidate,
    _permit_review_cell,
    _permit_scope,
    _permit_status_class,
    _permit_status_group,
    _permit_tik_link,
)
from .page_resources import COLLAPSE_TOP, _date_cell, _e, _iso


def _permits_section(
    permits: list[dict],
    rows_file: str | None = None,
    default_rows_file: str | None = None,
    evidence_tiks: frozenset = frozenset(),
    lang: str = "he",
    pre: str = "",
) -> str:
    """Separate DRAFT-labeled permit-requests section (issue: permit feed).
    A permit request is NOT a deposited plan; the section is visually and
    textually distinct from the plans table. Terminal requests (closed / rejected /
    permit issued) are hidden by default - the planner can no longer act
    on them - and revealed by one checkbox. Dates render dd.mm.yy with the
    ISO value kept in data-iso for filtering."""
    from .i18n import meta as _meta
    from .i18n import t as _t

    _dir = _meta(lang)["dir"]
    if not permits:
        return ""

    def _address_display(p):
        # #408: when the feed preserved the raw source fields, a street
        # address shows only if a street name exists; a neighborhood is
        # labeled as one, never disguised as an address. Rows from an older
        # feed carry only the legacy joined "address" string - shown as-is.
        if "rehovName" in p:
            street = (p.get("rehovName") or "").strip()
            if street:
                num = (p.get("mispBait") or "").strip()
                return f"{street} {num}".strip(), ""
            schuna = (p.get("schunaName") or "").strip()
            if schuna:
                return _t(lang, "permits.schuna", schuna=schuna), _t(
                    lang, "permits.no_exact_address"
                )
            return _t(lang, "permits.no_address"), ""
        return (p.get("address") or "").strip(), ""

    rows = []
    default_rows = []
    for p in permits:
        status = p.get("status") or ""
        group_key, _group_label, _group_default = _permit_status_group(status)
        scope = _permit_scope(p)
        sug = p.get("sugbakasha") or ""
        address_text, address_note = _address_display(p)
        address_note_html = (
            " <span class='pub-missing'>" + _e(address_note) + "</span>"
            if address_note
            else ""
        )
        if p.get("_map_missing"):
            address_note_html += (
                " <span class='pub-missing'>" + _t(lang, "permits.no_map") + "</span>"
            )
        active = "0" if status in _PERMIT_TERMINAL_STATUSES else "1"
        pub_iso = _iso(p.get("publication_start"))
        search = _e(
            " ".join(
                [
                    p.get("tik_num") or "",
                    p.get("address") or "",
                    p.get("schunaName") or "",
                    p.get("mahut") or "",
                    sug,
                    f"גוש {p.get('gush')}" if p.get("gush") else "",
                    f"חלקה {p.get('helka')}" if p.get("helka") else "",
                ]
            ).lower()
        )
        pub_end_iso = _iso(p.get("publication_end_planned"))
        if pub_iso:
            pubcat = "dated"
        elif status in _PERMIT_PUB_EVIDENCE_STATUSES or pub_end_iso:
            pubcat = "pub-nodate"
        else:
            pubcat = "no-evidence"
        pub_cell = (
            _date_cell(p.get("publication_start"))
            if pub_iso
            else "<span class='pub-missing'>"
            + _t(lang, "permits.pub_missing")
            + "</span>"
        )
        rows.append(
            f"<tr class='{('filtered-out' if active == '0' else '')}' data-active='{active}' data-status='{_e(status)}' data-sug='{_e(sug)}'"
            f" data-tik='{_e(p.get('tik_num') or '')}' data-group='{group_key}' data-scope='{scope}' data-statusdate='{_iso(p.get('status_date'))}'"
            f" data-pub='{pub_iso}' data-pubcat='{pubcat}' data-pubend='{pub_end_iso}' data-search='{search}'>"
            f"<td>{_permit_tik_link(p.get('tik_num'))}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_address'))}'>{_e(address_text)}{address_note_html}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_mahut'))}'>{_e(p.get('mahut') or '')}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_sug'))}'>{_e(sug)}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_status'))}'><span class=\"chip {_permit_status_class(status)}\">{_e(status)}</span></td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_statusdate'))}'>{_date_cell(p.get('status_date'))}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_pubstart'))}' data-publication-cell>{pub_cell}</td>"
            f"<td data-label='{_e(_t(lang, 'permits.mobile_pubend'))}'>{_date_cell(p.get('publication_end_planned'))}<span data-deadline-note></span></td>"
            f"<td data-label='{_e(_t(lang, 'permits.col_review'))}'>{_permit_review_cell(p.get('tik_num'), lang, pre)}</td></tr>"
        )
        if _is_default_permit_candidate(
            _group_default, scope, active, p.get("tik_num") or "", evidence_tiks
        ):
            default_rows.append(rows[-1])
    if default_rows_file:
        with open(default_rows_file, "w", encoding="utf-8") as fh:
            fh.write("".join(default_rows))
    if rows_file:  # full set loads client-side (#169); the page keeps only the top rows
        with open(rows_file, "w", encoding="utf-8") as fh:
            fh.write("".join(rows))
    body = "".join(rows[:COLLAPSE_TOP])
    n_terminal = sum(
        1 for p in permits if (p.get("status") or "") in _PERMIT_TERMINAL_STATUSES
    )

    def valid_coverage_date(value):
        try:
            datetime.date.fromisoformat(_iso(value))
            return True
        except (TypeError, ValueError):
            return False

    n_dated = sum(valid_coverage_date(p.get("publication_start")) for p in permits)
    n_planned = sum(
        valid_coverage_date(p.get("publication_end_planned")) for p in permits
    )
    coverage_text = _t(
        lang,
        "permits.coverage_text",
        total=len(permits),
        dated=n_dated,
        planned=n_planned,
        nodate=len(permits) - n_dated,
    )
    statuses = sorted({(p.get("status") or "") for p in permits if p.get("status")})
    from collections import Counter as _PCounter

    _gcounts = _PCounter(
        _permit_status_group(p.get("status") or "")[0] for p in permits
    )

    def _gchip(key: str, label: str, default_on: bool) -> str:
        sel = " sel" if default_on else ""
        dflt = " data-default='1'" if default_on else ""
        return (
            f'<span class="chip {_PERMIT_GROUP_CLASS[key]}{sel}" data-group="{key}"'
            f'{dflt} data-label="{_e(label)}">{_e(label)}'
            + ("" if key == "pubcheck" else f" ({_gcounts.get(key, 0)})")
            + "</span>"
        )

    main_chips: list[str] = []
    more_chips: list[str] = []
    for key, _he_label, _sts, default_on in PERMIT_STATUS_GROUPS:
        (main_chips if default_on else more_chips).append(
            _gchip(key, _t(lang, f"permits.group.{key}"), default_on)
        )
    if _gcounts.get("unmapped"):
        main_chips.append(
            _gchip("unmapped", _t(lang, "permitsjs.group_unmapped"), True)
        )
    plegend = (
        f'<div class="legend" id="pfgroups"><b>{_e(_t(lang, "permits.legend_groups"))}</b> '
        + " ".join(main_chips)
        + f' <details class="more-statuses"><summary>{_e(_t(lang, "permits.more_groups"))}</summary> '
        + '<div class="more-chips">'
        + " ".join(more_chips)
        + "</div></details></div>"
    )
    n_out_scope = sum(1 for p in permits if _permit_scope(p) == "out")
    sugs = sorted({(p.get("sugbakasha") or "") for p in permits if p.get("sugbakasha")})
    status_opts = (
        f"<option value=''>{_e(_t(lang, 'permits.status_all'))}</option>"
        + "".join(f"<option value='{_e(v)}'>{_e(v)}</option>" for v in statuses)
    )
    sug_opts = f"<option value=''>{_e(_t(lang, 'permits.sug_all'))}</option>" + "".join(
        f"<option value='{_e(v)}'>{_e(v)}</option>" for v in sugs
    )
    return f"""
<section id="permits" dir="{_dir}">
<h2>{_e(_t(lang, "permits.h2"))}</h2>
<p class="permits-note">{_t(lang, "permits.note_html")}</p>
{plegend}
<p class="permits-note" id="permit-group-help">{_t(lang, "permits.group_help")}</p>
<details id="permit-coverage"><summary>{_e(_t(lang, "permits.coverage_summary"))}</summary>
<p>{_e(_t(lang, "permits.coverage_p1"))}
<span id="permit-coverage-counts">{_e(coverage_text)}</span></p>
<p>{_t(lang, "permits.coverage_p2")}</p></details>
<div id="pfilters">
<input type="search" id="pfq" placeholder="{_e(_t(lang, "permits.search_placeholder"))}" title="{_e(_t(lang, "permits.search_title"))}">
<select id="pfstatus" aria-label="{_e(_t(lang, "permits.status_aria"))}">{status_opts}</select>
<select id="pfsug">{sug_opts}</select>
<label>{_e(_t(lang, "permits.from_label"))} <input type="date" id="pffrom"></label>
<label>{_e(_t(lang, "permits.to_label"))} <input type="date" id="pfto"></label>
<label><input type="checkbox" id="pfopenonly" checked> {_e(_t(lang, "permits.openonly"))}</label>
<label><input type="checkbox" id="pfscope"> {_e(_t(lang, "permits.scope", n=n_out_scope))}</label>
<label><input type="checkbox" id="pfclosed"> {_e(_t(lang, "permits.closed", n=n_terminal))}</label>
<button id="pfreset" type="button">{_e(_t(lang, "permits.reset"))}</button>
<button id="copy-permit-link" type="button">{_e(_t(lang, "permits.copy_link"))}</button>
<span id="pfcount"></span>
<span id="pfunknown"></span>
<span id="pfflag" class="pub-missing" style="display:none">{_e(_t(lang, "permits.flag_invalid"))}</span>
</div>
<table id="permits-table"><thead><tr>
<th>{_e(_t(lang, "permits.col_tik"))}</th><th>{_e(_t(lang, "permits.col_address"))}</th><th>{_e(_t(lang, "permits.col_mahut"))}</th><th>{_e(_t(lang, "permits.col_sug"))}</th><th>{_e(_t(lang, "permits.col_status"))}</th>
<th>{_e(_t(lang, "permits.col_statusdate"))}</th><th>{_e(_t(lang, "permits.col_pubstart"))}</th><th>{_e(_t(lang, "permits.col_pubend"))}</th>
<th title="{_e(_t(lang, "permits.col_review_title"))}">{_e(_t(lang, "permits.col_review"))}</th>
</tr></thead><tbody>{body}</tbody></table>
<noscript><p>{_e(_t(lang, "permits.noscript", n=COLLAPSE_TOP))}</p></noscript>
<button id="pmore" type="button"></button>
</section>"""
