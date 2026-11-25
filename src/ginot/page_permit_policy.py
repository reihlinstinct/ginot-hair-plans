"""Permit status, scope, publication evidence and public review policies."""

import json
import re
import urllib.parse as _urlparse_mod

from .page_resources import _e

# Section: Status groups and display classes


def _permit_status_class(status: str) -> str:
    """Colour class for a permit-request status (mirrors the plan chip palette)."""
    st = status or ""
    if "נסגרה" in st or st == "נדחתה":
        return "c-closed"
    if "הופק" in st:
        return "c-approved"
    if "פרסום" in st or "הודעות לפני תקנה" in st:
        return "c-deposit"
    if "וועד" in st or "ועדת" in st or "רשות הרישוי" in st:
        return "c-review"
    if "טיוטת היתר" in st:
        return "c-cond"
    return "c-inproc"


_PERMIT_PUB_EVIDENCE_STATUSES = frozenset(
    {
        "תום תקופת פרסום",
        "פורסמה בקשה להקלה",
    }
)


_PERMIT_TERMINAL_STATUSES = frozenset(
    {
        "נדחתה",
        "הבקשה נסגרה",
        "הופק-הוצא היתר בניה",
        "הופק היתר מוארך",
    }
)


# Issue #521: the feed carries ~25 raw request statuses; they group into a few
# objection-workflow stages. Only the objection-relevant groups are selected by
# default; the rest sit behind a "סטטוסים נוספים" disclosure. The raw status
# stays on every row and in the status select.
PERMIT_STATUS_GROUPS: tuple[tuple[str, str, frozenset, bool], ...] = (
    (
        "obj",
        "פרסום / הודעות להתנגדות",
        frozenset(
            {
                "תחילת פרסום הבקשה להקלה",
                "פורסמה בקשה להקלה",
                "תחילת הודעות לפני תקנה 36",
                "השלמת הודעות לפני תקנה 36",
            }
        ),
        True,
    ),
    ("pubcheck", "פרסום עירוני - דורש בדיקה", frozenset(), True),
    (
        "pre",
        "פרסום מתקרב",
        frozenset({"ממתין לאישור נוסח פרסום", "נוסח פרסום אושר"}),
        True,
    ),
    (
        "review",
        "בטיפול/דיונים",
        frozenset(
            {
                "נפתח תיק רישוי",
                "הגשה מקוונת הושלמה",
                "נדונה בוועדת המשנה",
                "נדונה ברשות הרישוי",
                "נדונה בועדת ערר",
                "התקבל ערר",
                "התקבלה בקשה לדיון המועצה",
                "חידוש טיפול בבקשה",
                "שולמה מקדמה",
                'אושר ע"י מהנדס העיר',
            }
        ),
        False,
    ),
    (
        "draft",
        "טיוטת היתר",
        frozenset({"הוכנה טיוטת היתר בניה", "התקבל תיק ורוד / מסמכים חתומים"}),
        False,
    ),
    ("postpub", "אחרי פרסום", frozenset({"תום תקופת פרסום"}), False),
    (
        "issued",
        "הופק היתר",
        frozenset({"הופק-הוצא היתר בניה", "הופק היתר מוארך"}),
        False,
    ),
    (
        "closed",
        "סגור/אחר",
        frozenset({"הבקשה נסגרה", "הבקשה נגנזה", "נדחתה", ""}),
        False,
    ),
)


_PERMIT_GROUP_CLASS = {
    "obj": "c-deposit",
    "pre": "c-review",
    "pubcheck": "c-inproc",
    "review": "c-inproc",
    "draft": "c-cond",
    "postpub": "c-inproc",
    "issued": "c-approved",
    "closed": "c-closed",
    "unmapped": "c-inproc",
}


def _permit_status_group(status: str) -> tuple[str, str, bool]:
    """(group key, group label, default-visible) for a raw permit status.
    An unmapped (e.g. newly added) status fails VISIBLE: missing an objection
    window is worse than extra noise (issue #521)."""
    st = status or ""
    for key, label, statuses, default_visible in PERMIT_STATUS_GROUPS:
        if st in statuses:
            return key, label, default_visible
    return "unmapped", "לא מסווג", True


# Section: Council scope and public identifiers


# Issue #521 (+ #529): scope flag by the council's 7 neighbourhoods
# (ginothair.org.il). "in" = one of the 7; "out" = another Jerusalem
# neighbourhood seen in the feed; "unknown" = no usable neighbourhood signal
# (kept visible by default - fail visible, never hide a possible objection).
_PERMIT_SCOPE_IN = frozenset(
    {
        "קטמון הישנה",
        "רחביה",
        "קריית שמואל",
        "מושבה גרמנית",
        "המושבה היוונית",
        "טלביה",
        "טלביה/המוגרבים",
        "נוה שאנן/ניות",
        "ניות",
    }
)


_PERMIT_SCOPE_OUT = frozenset(
    {
        "בית וגן",
        "בית צפפה",
        "גאולים - בקעה",
        "גבעת אורן",
        "גבעת הורדים",
        "גבעת המטוס",
        "גבעת הפורצים",
        "גבעת מרדכי",
        "גבעת רם",
        "גונן ב",
        "גונן ג",
        "גונן ה",
        "גונן ו",
        "גונן ח",
        "גונן ט",
        "גוננים",
        "גילה",
        "מנחת",
        "מקור חיים",
        "נוה גרנות",
        "סן סימון",
        "עומריה",
        "פת",
        "קרית האומה",
        "שרפת",
        "תלפיות",
        "תלפיות תעשיה",
    }
)


def _permit_scope(p: dict) -> str:
    """Scope flag for a permit row: in / out / unknown (issue #521).
    schunaName is definitive when present; otherwise the feed's legacy
    address string ends with the neighbourhood ("הפלמח 41 קטמון הישנה")."""
    schuna = (p.get("schunaName") or "").strip()
    if schuna:
        return "in" if schuna in _PERMIT_SCOPE_IN else "out"
    address = (p.get("address") or "").strip()
    if not address:
        return "unknown"
    for name in _PERMIT_SCOPE_IN:
        if address.endswith(name):
            return "in"
    for name in _PERMIT_SCOPE_OUT:
        if address.endswith(name):
            return "out"
    return "unknown"


def _permit_tik_link(tik_num: str | None) -> str:
    """Link a permit request number to its file in the municipality's
    licensing data viewer (תיק רישוי בניה, SystemCode 26400046). Issue #96."""
    tik = (tik_num or "").strip()
    if not tik:
        return ""
    url = (
        "https://ykpubdata.jerusalem.muni.il/#/Details?TikNum="
        + _urlparse_mod.quote(tik, safe="")
        + "&SystemCode=26400046&Page=BakashalInfo"
    )
    return f"<a href='{url}' target='_blank' rel='noopener'>{_e(tik)}</a>"


PERMIT_ID_RE = re.compile(r"^\d{4}/\d{4}\.\d{2}$")


def write_permit_ids(permits: list[dict], path: str) -> int:
    """Write the public list of permit request numbers (tik_num) the submit worker
    validates external reviews against (#515). Sorted, de-duplicated, no timestamp,
    so the file only changes when the set of requests changes. Returns the count."""
    ids = sorted(
        {
            str(p.get("tik_num") or "").strip()
            for p in permits
            if PERMIT_ID_RE.match(str(p.get("tik_num") or "").strip())
        }
    )
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ids": ids}, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    return len(ids)


# Section: Published community and AI review links


# Curated community sources, distinct from AI reviews and official notices.
COMMUNITY_SOURCE_CASES = frozenset({"101-1389568", "101-1377753", "1993/0664.03"})


COMMUNITY_SOURCE_URL = "reviews/forum-2026-10-14/summary-redacted.pdf"


COMMUNITY_SOURCE_RECORDS = (
    (COMMUNITY_SOURCE_CASES, COMMUNITY_SOURCE_URL, "14.10.26"),
    (
        frozenset({"101-1377753", "2026/0439.00", "101-1488261"}),
        "reviews/forum-2026-11-04-source/summary-redacted.pdf",
        "04.11.26",
    ),
    (
        frozenset({"101-1386671", "101-1348069"}),
        "reviews/forum-2026-11-18-source/summary-redacted.pdf",
        "18.11.26",
    ),
    (
        frozenset({"101-0779546"}),
        "reviews/forum-2022-04-04-source/summary-redacted.pdf",
        "04.04.22",
    ),
    (
        frozenset({"101-0932152"}),
        "reviews/forum-2022-07-25-source/summary-redacted.pdf",
        "25.07.22",
    ),
    (
        frozenset({"101-1071448"}),
        "reviews/forum-2022-11-14-source/summary-redacted.pdf",
        "14.11.22",
    ),
    (
        frozenset({"101-0182667"}),
        "reviews/forum-2024-02-07-source/summary-redacted.pdf",
        "07.02.24",
    ),
    (
        frozenset({"101-1024645"}),
        "reviews/forum-2024-03-06-source/summary-redacted.pdf",
        "06.03.24",
    ),
    (
        frozenset({"101-0973958"}),
        "reviews/forum-2024-05-29-source/summary-redacted.pdf",
        "29.05.24",
    ),
    (
        frozenset({"101-0973958"}),
        "reviews/forum-2024-06-26-source/summary-redacted.pdf",
        "26.06.24",
    ),
    (
        frozenset({"101-1301753"}),
        "reviews/forum-2024-11-27-source/summary-redacted.pdf",
        "27.11.24",
    ),
    (
        frozenset({"101-0995332"}),
        "reviews/forum-2025-07-02-source/summary-redacted.pdf",
        "02.07.25",
    ),
    (
        frozenset({"101-1395268"}),
        "reviews/forum-2025-10-29-source/summary-redacted.pdf",
        "29.10.25",
    ),
    (
        frozenset({"101-1437755"}),
        "reviews/forum-2025-11-26-source/summary-redacted.pdf",
        "26.11.25",
    ),
    (
        frozenset({"101-1336049", "101-1345420"}),
        "reviews/forum-2026-02-25-source/summary-redacted.pdf",
        "25.02.26",
    ),
    (
        frozenset({"101-0617134"}),
        "reviews/forum-2026-03-11-source/summary-redacted.pdf",
        "11.03.26",
    ),
    (
        frozenset({"101-1030790"}),
        "reviews/forum-2026-04-15-source/summary-redacted.pdf",
        "15.04.26",
    ),
    (
        frozenset({"101-1516707"}),
        "reviews/forum-2026-05-20-source/summary-redacted.pdf",
        "20.05.26",
    ),
    (
        frozenset({"101-0995332"}),
        "reviews/forum-2026-09-02-source/summary-redacted.pdf",
        "02.09.26",
    ),
    (
        frozenset({"101-1366053", "101-1404177"}),
        "reviews/forum-2026-09-09-source/summary-redacted.pdf",
        "09.09.26",
    ),
    (
        frozenset({"101-1446145"}),
        "reviews/forum-2026-09-23-source/summary-redacted.pdf",
        "23.09.26",
    ),
    (
        frozenset({"101-1214279"}),
        "reviews/forum-2026-09-30-source/summary-redacted.pdf",
        "30.09.26",
    ),
)


def _community_source_link(case_id, lang: str = "he", pre: str = ""):
    from .i18n import t as _tt

    return "".join(
        f" <a class='community-source' href='{pre}{url}' "
        f'title="{_e(_tt(lang, "cs.forum_title", date=date))}">'
        f"{_e(_tt(lang, 'cs.forum_text', date=date))}</a>"
        for cases, url, date in COMMUNITY_SOURCE_RECORDS
        if case_id in cases
    )


# Only already-published public reviews are linked. External/unreviewed
# submissions never become table links automatically.
PERMIT_AI_REVIEWS = {
    "2026/0439.00": "reviews/palmach41/review-2026-0439.00.html",
}


def _permit_review_cell(tik_num, lang: str = "he", pre: str = ""):
    from .i18n import t as _t

    url = PERMIT_AI_REVIEWS.get((tik_num or "").strip())
    source = _community_source_link((tik_num or "").strip(), lang, pre)
    if url:
        return (
            f"<a href='{pre}{_e(url)}' title='{_e(_t(lang, 'permits.review_link_title'))}'>"
            f"{_e(_t(lang, 'permits.col_review'))}</a>" + source
        )
    return (
        f'<span class="derived">{_e(_t(lang, "permits.review_none"))}</span>' + source
    )


# Section: Default subset and publication evidence


def _is_default_permit_candidate(
    group_default: bool, scope: str, active: str, tik: str, evidence_tiks: frozenset
) -> bool:
    """#441: a row the default (no-interaction) view may need without the full
    fragment. Default-visible groups (unmapped fails visible) that are active
    and not out of scope, plus every active row whose tik has publication
    evidence, because the #573 overlay can promote it into the "obj" group."""
    if active != "1":
        return False
    return (group_default and scope != "out") or tik in evidence_tiks


def publication_evidence_tiks(path: str) -> frozenset:
    """#441: tiks the #573 overlay may promote, read from the normalized
    publication list (data/publications_active.json). Every in-polygon entry
    counts regardless of its date: the client applies the freshness window
    against its own today, so the subset must not pre-filter by date. A missing
    or invalid list yields no evidence, the same as the page, which then has
    no overlay to apply."""
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError):
        return frozenset()
    if not isinstance(entries, list):
        return frozenset()
    return frozenset(
        e["tik_num"]
        for e in entries
        if isinstance(e, dict)
        and e.get("in_polygon") is True
        and isinstance(e.get("tik_num"), str)
        and e["tik_num"]
    )
