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
) -> str:
    """Separate DRAFT-labeled permit-requests section (issue: permit feed).
    A permit request is NOT a deposited plan; the section is visually and
    textually distinct from the plans table. Terminal requests (closed / rejected /
    permit issued) are hidden by default - the planner can no longer act
    on them - and revealed by one checkbox. Dates render dd.mm.yy with the
    ISO value kept in data-iso for filtering."""
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
                return f"שכונה: {schuna}", "לא צוינה כתובת מדויקת בתיק"
            return "כתובת לא זמינה", ""
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
            address_note_html += " <span class='pub-missing'>אין מיקום</span>"
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
            else "<span class='pub-missing'>תאריך פרסום חסר</span>"
        )
        rows.append(
            f"<tr class='{('filtered-out' if active == '0' else '')}' data-active='{active}' data-status='{_e(status)}' data-sug='{_e(sug)}'"
            f" data-tik='{_e(p.get('tik_num') or '')}' data-group='{group_key}' data-scope='{scope}' data-statusdate='{_iso(p.get('status_date'))}'"
            f" data-pub='{pub_iso}' data-pubcat='{pubcat}' data-pubend='{pub_end_iso}' data-search='{search}'>"
            f"<td>{_permit_tik_link(p.get('tik_num'))}</td>"
            f"<td>{_e(address_text)}{address_note_html}</td>"
            f"<td>{_e(p.get('mahut') or '')}</td>"
            f"<td>{_e(sug)}</td>"
            f'<td><span class="chip {_permit_status_class(status)}">{_e(status)}</span></td>'
            f"<td>{_date_cell(p.get('status_date'))}</td>"
            f"<td data-publication-cell>{pub_cell}</td>"
            f"<td>{_date_cell(p.get('publication_end_planned'))}<span data-deadline-note></span></td>"
            f"<td>{_permit_review_cell(p.get('tik_num'))}</td></tr>"
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
    coverage_text = (
        f"{len(permits)} בקשות במאגר; {n_dated} עם תאריך תחילת פרסום; "
        f"{n_planned} עם סיום פרסום מתוכנן; {len(permits) - n_dated} ללא תאריך תחילת פרסום."
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
    for key, label, _sts, default_on in PERMIT_STATUS_GROUPS:
        (main_chips if default_on else more_chips).append(
            _gchip(key, label, default_on)
        )
    if _gcounts.get("unmapped"):
        main_chips.append(_gchip("unmapped", "לא מסווג", True))
    plegend = (
        '<div class="legend" id="pfgroups"><b>קבוצות תצוגה:</b> '
        + " ".join(main_chips)
        + ' <details class="more-statuses"><summary>קבוצות נוספות</summary> '
        + '<div class="more-chips">'
        + " ".join(more_chips)
        + "</div></details></div>"
    )
    n_out_scope = sum(1 for p in permits if _permit_scope(p) == "out")
    sugs = sorted({(p.get("sugbakasha") or "") for p in permits if p.get("sugbakasha")})
    status_opts = "<option value=''>כל סטטוסי המקור</option>" + "".join(
        f"<option value='{_e(v)}'>{_e(v)}</option>" for v in statuses
    )
    sug_opts = "<option value=''>כל הסוגים</option>" + "".join(
        f"<option value='{_e(v)}'>{_e(v)}</option>" for v in sugs
    )
    return f"""
<section id="permits" dir="rtl">
<h2>בקשות היתר</h2>
<p class="permits-note">מקור: מערכת איתור הנתונים ברישוי של עיריית ירושלים.
בקשת היתר אינה תכנית מופקדת - ההתנגדות לבקשה מוגשת לפי הוראות הפרסום
(סעיף 149 לחוק התכנון והבניה) ובמועדים שבפרסום עצמו.
בקשות שהסתיימו (נסגרו או הופק היתר) מוסתרות כברירת מחדל.
כברירת מחדל מוצגות רק בקשות הרלוונטיות להתנגדות - פתוחות להתנגדויות או
לקראת פרסום - בשכונות גינות העיר; שאר הקבוצות זמינות תחת "קבוצות נוספות",
ובסימון "הצג גם מחוץ ל-7 השכונות". הסטטוס הגולמי מהמקור מוצג בכל שורה.
בקשות ללא תאריך פרסום ידוע נשארות גלויות ומסומנות - היעדר התאריך אינו ראיה
שהבקשה ישנה או שלא פורסמה.
פרסום עירוני מאומת משמש לסיווג התצוגה ולתאריך הפרסום גם כשהסטטוס הגולמי טרם עודכן;
אין בכך אישור למועד התנגדות שאינו ידוע.
מספר הבקשה מקשר לתיק במערכת
<a href='https://ykpubdata.jerusalem.muni.il/' target='_blank' rel='noopener'>איתור נתונים ברישוי של העירייה</a>.
עמודת סקירת AI מקשרת לסיכום אוטומטי כשפורסם; אינו מסמך רשמי ואינו הגשת התנגדות.</p>
{plegend}
<p class="permits-note" id="permit-group-help">הכפתורים מסננים לפי קבוצות תצוגה, לא לפי סטטוס מדויק.
קבוצת "פרסום / הודעות להתנגדות" כוללת שלבי פרסום מהמקור וגם בקשות עם פרסום עירוני מאומת,
אפילו אם סטטוס המקור שלהן שונה. בקשות בסטטוס "שולמה מקדמה" אינן מועברות לקבוצה זו:
פרסום עירוני שלהן מוצג בקבוצה נפרדת "פרסום עירוני - דורש בדיקה".
פרסום כשלעצמו אינו אישור שניתן להגיש התנגדות כעת.
לסינון סטטוס מדויק השתמשו ברשימה "כל סטטוסי המקור"; הסטטוס המקורי נשמר בכל שורה.</p>
<details id="permit-coverage"><summary>מקור הנתונים וכיסוי תאריכי הפרסום</summary>
<p>הטבלה כוללת את נתוני בקשות ההיתר ותאריכי שלבי הפרסום שנאספו ממערכת הרישוי העירונית.
<span id="permit-coverage-counts">{coverage_text}</span></p>
<p>הספירה מתייחסת לכל הבקשות שבמאגר, לפני סינון התצוגה.
תאריך פרסום חסר אינו מעיד שלא פורסמה בקשה.
סיום פרסום מתוכנן אינו מועד התנגדות מאומת; המועד בהודעת הפרסום המקורית הוא הקובע.
לא נוספו לכאן תיקים מהמראה החיצונית או מסמכי תיק.</p></details>
<div id="pfilters">
<input type="search" id="pfq" placeholder="חיפוש מספר / כתובת / מהות; או עם |" title="לחיפוש חלופות הפרידו עם |, למשל: פלמח 41 | פלמח 49. פסיק נשאר תו רגיל. החיפוש מתעלם מגרש ומרכאות (׳ ״ ' &quot; ’), ממקפים, מניקוד ומרווחים כפולים">
<select id="pfstatus" aria-label="סטטוס מדויק מהמקור">{status_opts}</select>
<select id="pfsug">{sug_opts}</select>
<label>מתאריך פרסום <input type="date" id="pffrom"></label>
<label>עד <input type="date" id="pfto"></label>
<label><input type="checkbox" id="pfopenonly" checked> רק מועד התנגדות שלא עבר</label>
<label><input type="checkbox" id="pfscope"> הצג גם מחוץ ל-7 השכונות ({n_out_scope})</label>
<label><input type="checkbox" id="pfclosed"> הצג בקשות שהסתיימו ({n_terminal})</label>
<button id="pfreset" type="button">נקה</button>
<button id="copy-permit-link" type="button">העתק קישור לסינון</button>
<span id="pfcount"></span>
<span id="pfunknown"></span>
<span id="pfflag" class="pub-missing" style="display:none">תאריך לא תקין - הוחזרה ברירת המחדל</span>
</div>
<table id="permits-table"><thead><tr>
<th>מספר בקשה</th><th>כתובת</th><th>מהות</th><th>סוג</th><th>סטטוס</th>
<th>תאריך סטטוס</th><th>תחילת פרסום</th><th>סיום פרסום (מתוכנן)</th>
<th title="סיכום שהופק באמצעות AI - אינו מסמך רשמי">סקירת AI</th>
</tr></thead><tbody>{body}</tbody></table>
<noscript><p>מוצגות {COLLAPSE_TOP} הבקשות הראשונות בלבד - להצגת כולן ולהשתמש בסינון יש להפעיל JavaScript.</p></noscript>
<button id="pmore" type="button"></button>
</section>"""
