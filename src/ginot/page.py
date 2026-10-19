"""Render the static public page (Hebrew RTL) + Atom feed from the plan table.

Sorted by receiving_date desc ("order of entry into the system"). The
objection-deadline column is marked as derived (deposit publication + 60d).
"""
import datetime
import html
import json

ACTIVE_STATUSES = ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")


def _bars(counts: dict, label_map: dict | None = None) -> str:
    """Pure-CSS horizontal bars, no external services."""
    if not counts:
        return "<p>אין נתונים</p>"
    top = max(counts.values())
    out = []
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        label = (label_map or {}).get(k, k) or "(ללא)"
        pct = max(2, round(100 * v / top))
        out.append(f"<div class='bar'><span class='bl'>{_e(label)}</span>"
                   f"<span class='bt'><span class='bf' style='width:{pct}%'></span></span>"
                   f"<span class='bv'>{v}</span></div>")
    return "<div class='bars'>" + "".join(out) + "</div>"


def _month_key(iso: str) -> str:
    return iso[:7] if iso and len(iso) >= 7 else ""


def stats_section(rows: list[dict]) -> str:
    from collections import Counter
    by_status = Counter(r.get("station_desc") or "(ללא)" for r in rows)
    by_flag = Counter(r.get("inside_flag") or "(ללא)" for r in rows)
    deposits = Counter(filter(None, (_month_key(r.get("pl_last_deposit_date") or r.get("depositing_date")) for r in rows)))
    deposits = dict(sorted(deposits.items())[-24:])
    approvals = Counter(filter(None, ((r.get("pl_date_8_approval") or "")[:4] for r in rows)))
    approvals = dict(sorted(approvals.items()))
    flag_he = {"inside": "בתוך השטח", "partial": "חפיפה חלקית"}
    return f"""<h2>סטטיסטיקה</h2>
<div class="stats">
<div><h3>לפי סטטוס</h3>{_bars(dict(by_status))}</div>
<div><h3>בתוך השטח / חפיפה חלקית</h3>{_bars(dict(by_flag), flag_he)}</div>
<div><h3>הפקדות לפי חודש (24 אחרונים)</h3>{_bars(deposits)}</div>
<div><h3>אישורים לפי שנה</h3>{_bars(approvals)}</div>
</div>"""



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
                f"<td>{_e(r['pl_area_dunam'])}</td><td>{_e(r['inside_flag'])}</td></tr>")

    new_ids = {c["pl_number"] for c in changes if c["kind"] == "new"}
    body = "\n".join(tr(r, "new" if r["pl_number"] in new_ids else "") for r in rows)
    stats_html = stats_section(rows)
    urgent = [r for r in rows if r.get("advisory_urgent")]
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
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:1em}}
.bars .bar{{display:flex;align-items:center;gap:6px;margin:2px 0}}
.bars .bl{{width:12em;font-size:12px;text-align:left;direction:ltr}}
.bars .bt{{flex:1;background:#eee;height:12px}}
.bars .bf{{display:block;background:#4a7; height:12px}}
.bars .bv{{font-size:12px;width:3em}}
</style></head><body>
<h1>תכניות תכנון ובנייה בשטח המינהל הקהילתי {_e(council_name)}</h1>
<p>מסודר לפי תאריך קליטה במערכת (חדש קודם). עודכן: {_e(generated)}.
מקור: שירות התכנון הציבורי (iplan) - נתונים משוערים, לצורכי מידע בלבד.</p>
<p>עמודת "אחרון להתנגדות" היא <b>הערכה מחושבת</b> (פרסום הפקדה + 60 יום) - לבדיקה מול המו"ת.</p>
{stats_html}
<h2>דחוף להתנגדות</h2><ul>{urgent_html}</ul>
<h2>שינויים אחרונים</h2><ul>{changes_html}</ul>
<table><thead><tr><th>מספר תכנית</th><th>שם</th><th>סטטוס</th><th>קליטה</th>
<th>הפקדה</th><th>אחרון להתנגדות (משוער)</th><th>שטח (דונם)</th><th>בתוך/חלקי</th></tr></thead>
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
