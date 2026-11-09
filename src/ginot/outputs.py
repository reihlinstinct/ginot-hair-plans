"""Build the plan table (CSV/XLSX rows) from ArcGIS features.

Objection deadlines (both DERIVED from the publication of the deposit notice):
- objection_deadline_derived_60d_from_publication: +60 days, the legacy
  conservative display basis.
- objection_deadline_derived_2m_from_publication: +2 calendar months, the
  statutory window for deposited plans (Planning and Building Law 5725-1965
  s.102: "תוך חודשיים" from the latest newspaper publication), computed per
  Interpretation Law 5741-1981 s.10(b): the period ends on the same
  day-of-month in the final month, or the final month's last day when short.
  Rest-day postponement (s.10(c)) is deliberately NOT applied: the true final
  day can then only be later than this derived date, which stays on the safe
  (earlier) side for filers. Flagged as derived in the column name; only
  meaningful for plans in הפקדה status.
"""

import calendar
import csv
import datetime

from shapely.geometry import Polygon
from shapely.ops import unary_union

DAY = 86400
OBJECTION_WINDOW_DAYS = 60
OBJECTION_WINDOW_MONTHS = 2
INSIDE_FRACTION = 0.995


def _iso(ms):
    if not ms:
        return ""
    return datetime.datetime.fromtimestamp(
        ms / 1000, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")


def _plus_days(ms, days):
    if not ms:
        return ""
    return datetime.datetime.fromtimestamp(
        ms / 1000 + days * DAY, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%d")


def _plus_months(iso: str, months: int) -> str:
    """Calendar-month arithmetic per Interpretation Law 5741-1981 s.10(b).

    The period ends on the same day-of-month in the final month; when that
    month is short, it ends on its last day (e.g. 31.12 + 2m -> 28/29.02).
    """
    if not iso:
        return ""
    d = datetime.date.fromisoformat(iso)
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return datetime.date(y, m, min(d.day, last)).isoformat()


COLUMNS = [
    "pl_number",
    "pl_name",
    "station_desc",
    "internet_short_status",
    "entity_subtype_desc",
    "receiving_date",
    "open_date",
    "date_saf",
    "depositing_date",
    "pl_last_deposit_date",
    "pl_date_advertise",
    "pl_date_8_approval",
    "objection_deadline_derived_60d_from_publication",
    "objection_deadline_derived_2m_from_publication",
    "pl_area_dunam",
    "intersection_dunam",
    "inside_flag",
    "mavat_url",
    "mp_id",
    "jurstiction_area_name",
    "last_update_date",
]


def row_from_feature(attrs: dict, geom: dict | None, council: Polygon | None) -> dict:
    inside, inter_dunam = "", ""
    if geom and geom.get("rings") and council is not None:
        pg = unary_union([Polygon(r) for r in geom["rings"]])
        inter = pg.intersection(council).area
        inside = (
            "inside" if (pg.area and inter / pg.area > INSIDE_FRACTION) else "partial"
        )
        inter_dunam = round(inter / 1000, 1)
    # s.102 objection clock runs from newspaper publication only. depositing_date
    # is the committee's deposit DECISION date; deriving a deadline from it shows
    # a bogus statutory date for plans still awaiting publication (issue: 12/12
    # shown for plans whose deposit was only decided on 13/10/2026).
    pub = attrs.get("pl_date_advertise") or attrs.get("pl_last_deposit_date")
    return {
        "pl_number": attrs.get("pl_number"),
        "pl_name": attrs.get("pl_name"),
        "station_desc": attrs.get("station_desc"),
        "internet_short_status": attrs.get("internet_short_status"),
        "entity_subtype_desc": attrs.get("entity_subtype_desc"),
        "receiving_date": _iso(attrs.get("receiving_date")),
        "open_date": _iso(attrs.get("open_date")),
        "date_saf": _iso(attrs.get("date_saf")),
        "depositing_date": _iso(attrs.get("depositing_date")),
        "pl_last_deposit_date": _iso(attrs.get("pl_last_deposit_date")),
        "pl_date_advertise": _iso(attrs.get("pl_date_advertise")),
        "pl_date_8_approval": _iso(attrs.get("pl_date_8")),
        "objection_deadline_derived_60d_from_publication": _plus_days(
            pub, OBJECTION_WINDOW_DAYS
        ),
        "objection_deadline_derived_2m_from_publication": _plus_months(
            _iso(pub), OBJECTION_WINDOW_MONTHS
        ),
        "pl_area_dunam": attrs.get("pl_area_dunam"),
        "intersection_dunam": inter_dunam,
        "inside_flag": inside,
        "mavat_url": attrs.get("pl_url"),
        "mp_id": attrs.get("mp_id"),
        "jurstiction_area_name": attrs.get("jurstiction_area_name"),
        "last_update_date": _iso(attrs.get("last_update_date")),
    }


def rows_from_features(features: list[dict], council: Polygon | None) -> list[dict]:
    rows = [
        row_from_feature(f["attributes"], f.get("geometry"), council) for f in features
    ]
    rows.sort(key=lambda r: (r["receiving_date"] or "9999", r["pl_number"] or ""))
    return rows


def write_csv(rows: list[dict], path: str):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_xlsx(rows: list[dict], path: str):
    from collections import Counter

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "plans"
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r[c] for c in COLUMNS])
    ws2 = wb.create_sheet("counts")
    ws2.append(["station_desc", "count"])
    for k, v in Counter(r["station_desc"] for r in rows).most_common():
        ws2.append([k, v])
    ws2.append([])
    ws2.append(["inside_flag", "count"])
    for k, v in Counter(r["inside_flag"] for r in rows).most_common():
        ws2.append([k, v])
    wb.save(path)
