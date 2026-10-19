"""Render the static public page (Hebrew RTL) + Atom feed from the plan table.

Default row order: derived objection deadline, farthest first (plans
without a deadline below those with one). Clicking a column header sorts
by that column's true values (dates sort as dates, not text). Approved (non-active) plans are hidden by
default (one click to bring back, count stated on the page). The table
collapses to the top 20 rows of the visible set with a show-more control;
client-side filters (status, inside/partial, date range, free text,
objection-open, show-approved) always operate over all rows.
Dates display as DD.MM.YYYY; ISO values stay in data-* attributes so all
sorting/filtering uses true dates. Statistics render below the table.
"""
import datetime
import html
import json

ACTIVE_STATUSES = ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")
DEPOSIT_MARK = "הפקדה"
COLLAPSE_TOP = 20

_CSS = """
body{font-family:system-ui,Arial;max-width:1100px;margin:1em auto;padding:0 1em}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px;font-size:14px}
th{background:#eee;position:sticky;top:0}
th button{background:none;border:0;font:inherit;cursor:pointer;padding:0}
th button.sorted-asc::after{content:" ▲"}th button.sorted-desc::after{content:" ▼"}
.chip{border-radius:8px;padding:1px 8px;background:#e0e0e0;color:#1a1a1a;white-space:nowrap}
.chip.c-deposit{background:#ffd27f}.chip.c-review{background:#cfe3ff}
.chip.c-cond{background:#e2d4f7}.chip.c-decision{background:#ffc4a8}
.chip.c-inproc{background:#bfe8d4}.chip.c-approved{background:#cfe8cf}
.legend{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px;margin:4px 0 8px}
.derived{color:#666}.new td{background:#fff8e1}
#filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 8px;
padding:8px;border:1px solid #ddd;border-radius:8px;background:#fafafa}
#filters input[type=search]{flex:1;min-width:180px}
#fcount{font-size:12px;color:#555}
#more{margin:6px 0;padding:6px 14px}
tr.filtered-out{display:none}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:1em}
.bars .bar{display:flex;align-items:center;gap:6px;margin:2px 0}
.bars .bl{width:12em;font-size:12px;text-align:left;direction:ltr}
.bars .bt{flex:1;background:#eee;height:12px}
.bars .bf{display:block;background:#4a7;height:12px}
.bars .bv{font-size:12px;width:3em}
"""

_JS = """
(function(){
var rows=Array.prototype.slice.call(document.querySelectorAll('#plans tbody tr'));
var fq=document.getElementById('fq'),fstatus=document.getElementById('fstatus'),
fflag=document.getElementById('fflag'),fobj=document.getElementById('fobj'),
ffrom=document.getElementById('ffrom'),fto=document.getElementById('fto'),
fappr=document.getElementById('fappr'),fcount=document.getElementById('fcount'),
more=document.getElementById('more');
var expanded=false;
function match(r){
  if(!fappr.checked&&r.getAttribute('data-active')!=='1')return false;
  var q=fq.value.trim().toLowerCase();
  if(q&&r.getAttribute('data-search').indexOf(q)===-1)return false;
  if(fstatus.value&&r.getAttribute('data-status')!==fstatus.value)return false;
  if(fflag.value&&r.getAttribute('data-flag')!==fflag.value)return false;
  if(fobj.checked&&r.getAttribute('data-open')!=='1')return false;
  var a=r.getAttribute('data-recv'),b=r.getAttribute('data-dep');
  if(ffrom.value&&!((a&&a>=ffrom.value)||(b&&b>=ffrom.value)))return false;
  if(fto.value&&!((a&&a<=fto.value)||(b&&b<=fto.value)))return false;
  return true;
}
function apply(){
  var n=0;
  rows.forEach(function(r){
    var vis=match(r);
    if(vis){n++;if(!expanded&&n>20)vis=false;}
    r.classList.toggle('filtered-out',!vis);
  });
  more.style.display=n>20?'':'none';
  more.textContent=expanded?'הצג 20 הראשונות':'הצג את כל '+n+' התכניות';
  fcount.textContent='מציג '+Math.min(n,expanded?n:20)+' מתוך '+n;
}
[fq,fstatus,fflag,fobj,ffrom,fto,fappr].forEach(function(el){
  var h=function(){expanded=false;apply();};
  el.addEventListener('input',h);el.addEventListener('change',h);
});
document.getElementById('freset').addEventListener('click',function(){
  fq.value='';fstatus.value='';fflag.value='';fobj.checked=false;fappr.checked=false;
  ffrom.value='';fto.value='';expanded=false;apply();
});
more.addEventListener('click',function(){expanded=!expanded;apply();});
var sortKey='obj',sortDir=-1;
function val(r,k){
  if(k==='area')return parseFloat(r.getAttribute('data-area'))||0;
  if(k==='num')return r.getAttribute('data-num');
  return r.getAttribute('data-'+k)||'';
}
function resort(){
  var tb=document.querySelector('#plans tbody');
  rows.sort(function(a,b){
    var x=val(a,sortKey),y=val(b,sortKey);
    if(!x&&!y)return 0;if(!x)return 1;if(!y)return -1;
    return (x<y?-1:x>y?1:0)*sortDir;
  });
  rows.forEach(function(r){tb.appendChild(r);});
  document.querySelectorAll('th button').forEach(function(b){
    b.classList.toggle('sorted-asc',b.getAttribute('data-sort')===sortKey&&sortDir===1);
    b.classList.toggle('sorted-desc',b.getAttribute('data-sort')===sortKey&&sortDir===-1);
  });
  apply();
}
document.querySelectorAll('th button').forEach(function(b){
  b.addEventListener('click',function(){
    var k=b.getAttribute('data-sort');
    if(sortKey===k){sortDir=-sortDir;}else{sortKey=k;sortDir=1;}
    expanded=false;resort();
  });
});
resort();
})();
"""


def _e(s):
    return html.escape(str(s or ""))


def _iso(d) -> str:
    d = (d or "").strip()
    return d if len(d) >= 10 and d[4] == "-" and d[7] == "-" else ""


def _fmt(d) -> str:
    iso = _iso(d)
    return f"{iso[8:10]}.{iso[5:7]}.{iso[2:4]}" if iso else ""


def _date_cell(d) -> str:
    iso = _iso(d)
    return f"<span dir='ltr' data-iso='{iso}'>{_e(_fmt(d))}</span>" if iso else ""


def _deposit_date(r) -> str:
    return r.get("pl_last_deposit_date") or r.get("depositing_date") or ""


def _is_open_objection(r, today: str) -> bool:
    st = r.get("station_desc") or ""
    deadline = _iso(r.get("objection_deadline_derived_60d_from_publication"))
    return bool(DEPOSIT_MARK in st and deadline and deadline >= today)


def _is_active(r) -> bool:
    st = r.get("station_desc") or ""
    return any(k in st for k in ACTIVE_STATUSES)


def _inside_rank(r) -> int:
    return 0 if r.get("inside_flag") == "inside" else 1


def sort_rows(rows: list[dict], today: str | None = None) -> list[dict]:
    """Default table order: derived objection deadline, farthest first; rows
    without a deadline sort below those with one (then newest entry first).
    Annotates each row with _rank (1-based) and _open_obj (window open today)."""
    today = today or datetime.date.today().isoformat()
    for r in rows:
        r["_open_obj"] = _is_open_objection(r, today)
    with_dl = sorted((r for r in rows if _iso(r.get("objection_deadline_derived_60d_from_publication"))),
                     key=lambda r: _iso(r["objection_deadline_derived_60d_from_publication"]), reverse=True)
    without_dl = sorted((r for r in rows if not _iso(r.get("objection_deadline_derived_60d_from_publication"))),
                        key=lambda r: _iso(r.get("receiving_date")), reverse=True)
    ordered = with_dl + without_dl
    for i, r in enumerate(ordered):
        r["_rank"] = i + 1
    return ordered


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




def _permits_section(permits: list[dict]) -> str:
    """Separate DRAFT-labeled permit-requests section (issue: permit feed).
    A permit request is NOT a deposited plan; the section is visually and
    textually distinct from the plans table."""
    if not permits:
        return ""
    body = "".join(
        f"<tr><td>{_e(p.get('tik_num') or '')}</td>"
        f"<td>{_e(p.get('address') or '')}</td>"
        f"<td>{_e(p.get('mahut') or '')}</td>"
        f"<td>{_e(p.get('sugbakasha') or '')}</td>"
        f"<td>{_e(p.get('status') or '')}</td>"
        f"<td>{_e(p.get('status_date') or '')}</td>"
        f"<td>{_e(p.get('publication_start') or '')}</td>"
        f"<td>{_e(p.get('publication_end_planned') or '')}</td></tr>"
        for p in permits)
    return f"""
<section id="permits" dir="rtl">
<h2>בקשות היתר (טיוטה - DRAFT)</h2>
<p class="permits-note">מקור: מערכת איתור הנתונים ברישוי של עיריית ירושלים.
בקשת היתר אינה תכנית מופקדת - ההתנגדות לבקשה מוגשת לפי הוראות הפרסום
(סעיף 149 לחוק התכנון והבניה) ובמועדים שבפרסום עצמו.</p>
<table id="permits-table"><thead><tr>
<th>מספר בקשה</th><th>כתובת</th><th>מהות</th><th>סוג</th><th>סטטוס</th>
<th>תאריך סטטוס</th><th>תחילת פרסום</th><th>סיום פרסום (מתוכנן)</th>
</tr></thead><tbody>{body}</tbody></table>
</section>"""

def render_index(rows: list[dict], changes: list[dict], generated: str, council_name: str,
                 permits: list[dict] | None = None) -> str:
    rows = sort_rows(rows)
    statuses = sorted({(r.get("station_desc") or "") for r in rows} - {""})

    def chip(st):
        st = st or ""
        if "הפקדה" in st:
            cls = "c-deposit"
        elif "בדיקה" in st:
            cls = "c-review"
        elif "תנאים" in st:
            cls = "c-cond"
        elif "הכרעה" in st:
            cls = "c-decision"
        elif "בהליך" in st:
            cls = "c-inproc"
        elif "אישור" in st:
            cls = "c-approved"
        else:
            cls = ""
        return f'<span class="chip {cls}">{_e(st)}</span>'

    def tr(r):
        search = _e((r["pl_number"] + " " + (r.get("pl_name") or "")).lower())
        attrs = (f"data-status='{_e(r.get('station_desc'))}' data-flag='{_e(r.get('inside_flag'))}' "
                 f"data-recv='{_e(_iso(r.get('receiving_date')))}' data-dep='{_e(_iso(_deposit_date(r)))}' "
                 f"data-open='{1 if r['_open_obj'] else 0}' data-obj='{_e(_iso(r['objection_deadline_derived_60d_from_publication']))}' data-num='{_e(r['pl_number'])}' data-name='{_e((r.get('pl_name') or '').lower())}' data-area='{_e(r['pl_area_dunam'])}' "
                 f"data-active='{1 if r['_open_obj'] or _is_active(r) else 0}' data-search='{search}'")
        cls = "new" if r.get("_is_new") else ""
        return (f"<tr class='{cls}' {attrs}>"
                f"<td><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a></td>"
                f"<td>{_e(r['pl_name'])}</td><td>{chip(r['station_desc'])}</td>"
                f"<td>{_date_cell(r['receiving_date'])}</td>"
                f"<td>{_date_cell(_deposit_date(r))}</td>"
                f"<td class='derived'>{_date_cell(r['objection_deadline_derived_60d_from_publication'])}</td>"
                f"<td>{_e(r['pl_area_dunam'])}</td><td>{_e(r['inside_flag'])}</td></tr>")

    new_ids = {c["pl_number"] for c in changes if c["kind"] == "new"}
    for r in rows:
        r["_is_new"] = r["pl_number"] in new_ids
    body = "\n".join(tr(r) for r in rows)
    stats_html = stats_section(rows)
    urgent = [r for r in rows if r.get("advisory_urgent")]
    urgent_html = "".join(
        f"<li><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a> {_e(r['pl_name'])} - "
        f"אחרון להתנגדות (משוער): {_e(_fmt(r['objection_deadline_derived_60d_from_publication']))}</li>"
        for r in urgent) or "<li>אין</li>"
    changes_html = "".join(
        f"<li>{_e(c['kind'])}: <a href='{_e(c['mavat_url'])}'>{_e(c['pl_number'])}</a> {_e(c['pl_name'])}"
        + (f" ({_e(c.get('from'))} → {_e(c.get('to'))})" if c["kind"] == "status_change" else "")
        + "</li>" for c in changes) or "<li>אין שינויים מהסריקה הקודמת</li>"
    status_opts = "".join(f"<option value='{_e(s)}'>{_e(s)}</option>" for s in statuses)
    n_approved = sum(1 for r in rows if not r["_open_obj"] and not _is_active(r))
    legend = '<div class="legend"><b>מקרא סטטוסים:</b> ' + " ".join(chip(s) for s in statuses) + "</div>"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>תכניות במינהל הקהילתי {_e(council_name)}</title>
<link rel="alternate" type="application/atom+xml" href="feed.xml">
<style>{_CSS}</style></head><body>
<h1>תכניות תכנון ובנייה בשטח המינהל הקהילתי {_e(council_name)}</h1>
<p>עודכן: {_e(generated)}. מקור: שירות התכנון הציבורי (iplan) - נתונים משוערים, לצורכי מידע בלבד.</p>
<p><b>סדר ברירת המחדל:</b> לפי "אחרון להתנגדות" (משוער) - התאריך הרחוק ביותר למעלה;
תכניות ללא תאריך יעד להתנגדות מופיעות מתחת לאלה שיש להן. לחיצה על כותרת עמודה ממיינת לפיה.
מוצגות {COLLAPSE_TOP} התכניות הרלוונטיות ביותר; סינון וחיפוש פועלים על כל התכניות.
תכניות מאושרות ({n_approved}) מוסתרות כברירת מחדל - סמנו "הצג תכניות מאושרות" כדי לראותן.</p>
<p>עמודת "אחרון להתנגדות" היא <b>הערכה מחושבת</b> (פרסום הפקדה + 60 יום) - לבדיקה מול המו"ת.</p>
{legend}
<div id="filters">
<input id="fq" type="search" placeholder="חיפוש חופשי (מספר / שם)">
<select id="fstatus"><option value="">כל הסטטוסים</option>{status_opts}</select>
<select id="fflag"><option value="">בתוך + חלקי</option><option value="inside">בתוך השטח</option><option value="partial">חפיפה חלקית</option></select>
<label><input type="checkbox" id="fobj"> חלון התנגדות פתוח (משוער)</label>
<label><input type="checkbox" id="fappr"> הצג תכניות מאושרות ({n_approved})</label>
<label>מתאריך <input type="date" id="ffrom"></label>
<label>עד <input type="date" id="fto"></label>
<button id="freset" type="button">נקה סינון</button>
<span id="fcount"></span>
</div>
<table id="plans"><thead><tr><th><button type="button" data-sort="num">מספר תכנית</button></th>
<th><button type="button" data-sort="name">שם</button></th>
<th><button type="button" data-sort="status">סטטוס</button></th>
<th><button type="button" data-sort="recv">קליטה</button></th>
<th><button type="button" data-sort="dep">הפקדה</button></th>
<th><button type="button" data-sort="obj">אחרון להתנגדות (משוער)</button></th>
<th><button type="button" data-sort="area">שטח (דונם)</button></th>
<th><button type="button" data-sort="flag">בתוך/חלקי</button></th></tr></thead>
<tbody>{body}</tbody></table>
<button id="more" type="button">הצג את כל {len(rows)} התכניות</button>
{_permits_section(permits or [])}
<h2>דחוף להתנגדות</h2><ul>{urgent_html}</ul>
<h2>שינויים אחרונים</h2><ul>{changes_html}</ul>
{stats_html}
<script>{_JS}</script>
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
                council_name: str = "גינות העיר", base_url: str = "",
                permits_path: str | None = None):
    import os
    os.makedirs(out_dir, exist_ok=True)
    generated = datetime.date.today().isoformat()
    permits = []
    if permits_path:
        try:
            with open(permits_path, encoding="utf-8") as pf:
                permits = json.load(pf).get("requests", [])
        except (FileNotFoundError, json.JSONDecodeError):
            permits = []
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(rows, changes, generated, council_name, permits))
    with open(f"{out_dir}/feed.xml", "w", encoding="utf-8") as fh:
        fh.write(render_feed(changes, generated, council_name, base_url))
    with open(f"{out_dir}/data.json", "w", encoding="utf-8") as fh:
        json.dump({"generated": generated, "rows": rows, "changes": changes,
                   "permits": permits}, fh, ensure_ascii=False)
