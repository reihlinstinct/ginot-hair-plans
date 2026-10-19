"""Render the static public page (Hebrew RTL) + Atom feed from the plan table.

Sorted by receiving_date desc ("order of entry into the system"). The
objection-deadline column is marked as derived (deposit publication + 60d).
"""
import datetime
import html
import json

ACTIVE_STATUSES = ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")
TRACKING_HE = {"new": "חדש", "reviewed": "נבדק", "objection_filed": "הוגשה התנגדות",
               "no_objection_needed": "אין צורך בהתנגדות", "urgent": "דחוף"}


def _e(s):
    return html.escape(str(s or ""))


def render_index(rows: list[dict], changes: list[dict], generated: str, council_name: str) -> str:
    def chip(st):
        cls = "active" if any(k in (st or "") for k in ACTIVE_STATUSES) else "approved"
        return f'<span class="chip {cls}">{_e(st)}</span>'

    def tr(r, cls=""):
        return (f"<tr class='{cls}'>"
                f"<td><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a></td>"
                f"<td>{_e(r['pl_name'])}</td><td>{chip(r['station_desc'])}</td>"
                f"<td>{_e(r['receiving_date'])}</td>"
                f"<td>{_e(r['pl_last_deposit_date'] or r['depositing_date'])}</td>"
                f"<td class='derived'>{_e(r['objection_deadline_derived_60d_from_publication'])}</td>"
                f"<td>{_e(r['pl_area_dunam'])}</td><td>{_e(r['inside_flag'])}</td>"
                f"<td>{_e(TRACKING_HE.get(r.get('tracking_state'), r.get('tracking_state') or ''))}</td></tr>")

    new_ids = {c["pl_number"] for c in changes if c["kind"] == "new"}
    body = "\n".join(tr(r, "new" if r["pl_number"] in new_ids else "") for r in rows)
    urgent = [r for r in rows if r.get("tracking_state") == "urgent"]
    urgent_html = "".join(
        f"<li><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a> {_e(r['pl_name'])} - "
        f"אחרון להתנגדות (משוער): {_e(r['objection_deadline_derived_60d_from_publication'])}</li>"
        for r in urgent) or "<li>אין</li>"
    changes_html = "".join(
        f"<li>{_e(c['kind'])}: <a href='{_e(c['mavat_url'])}'>{_e(c['pl_number'])}</a> {_e(c['pl_name'])}"
        + (f" ({_e(c.get('from'))} → {_e(c.get('to'))})" if c["kind"] == "status_change" else "")
        + "</li>" for c in changes) or "<li>אין שינויים מהסריקה הקודמת</li>"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>תכניות במינהל הקהילתי {_e(council_name)}</title>
<link rel="alternate" type="application/atom+xml" href="feed.xml">
<style>
body{{font-family:system-ui,Arial;max-width:1100px;margin:1em auto;padding:0 1em}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:4px 8px;font-size:14px}}
th{{background:#eee;position:sticky;top:0}}
.chip{{border-radius:8px;padding:1px 8px;background:#ddd}}
.chip.active{{background:#ffd27f}}.chip.approved{{background:#cfe8cf}}
.derived{{color:#666}}.new td{{background:#fff8e1}}
</style></head><body>
<h1>תכניות תכנון ובנייה בשטח המינהל הקהילתי {_e(council_name)}</h1>
<p>מסודר לפי תאריך קליטה במערכת (חדש קודם). עודכן: {_e(generated)}.
מקור: שירות התכנון הציבורי (iplan) - נתונים משוערים, לצורכי מידע בלבד.</p>
<p>עמודת "אחרון להתנגדות" היא <b>הערכה מחושבת</b> (פרסום הפקדה + 60 יום) - לבדיקה מול המו"ת.</p>
<h2>דחוף להתנגדות</h2><ul>{urgent_html}</ul>
<h2>שינויים אחרונים</h2><ul>{changes_html}</ul>
<table><thead><tr><th>מספר תכנית</th><th>שם</th><th>סטטוס</th><th>קליטה</th>
<th>הפקדה</th><th>אחרון להתנגדות (משוער)</th><th>שטח (דונם)</th><th>בתוך/חלקי</th><th>מעקב</th></tr></thead>
<tbody>{body}</tbody></table>
</body></html>"""


def render_feed(changes: list[dict], generated: str, council_name: str, base_url: str = "") -> str:
    entries = "".join(f"""<entry><title>{_e(c['kind'])}: {_e(c['pl_number'])} {_e(c['pl_name'])}</title>
<link href="{_e(c['mavat_url'])}"/><id>urn:ginot:{_e(c['pl_number'])}:{_e(c['kind'])}:{_e(generated)}</id>
<updated>{_e(generated)}T00:00:00Z</updated></entry>""" for c in changes)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="he">
<title>תכניות חדשות - {_e(council_name)}</title><id>{_e(base_url or 'urn:ginot:feed')}</id>
<updated>{_e(generated)}T00:00:00Z</updated>{entries}</feed>"""


def render_site(rows: list[dict], changes: list[dict], out_dir: str,
                council_name: str = "גינות העיר", base_url: str = ""):
    import os
    os.makedirs(out_dir, exist_ok=True)
    generated = datetime.date.today().isoformat()
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(rows, changes, generated, council_name))
    with open(f"{out_dir}/feed.xml", "w", encoding="utf-8") as fh:
        fh.write(render_feed(changes, generated, council_name, base_url))
    with open(f"{out_dir}/data.json", "w", encoding="utf-8") as fh:
        json.dump({"generated": generated, "rows": rows, "changes": changes}, fh, ensure_ascii=False)
