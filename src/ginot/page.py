"""Render the static public page (Hebrew RTL) + Atom feed from the plan table.

Default row order: derived objection deadline, farthest first (plans
without a deadline below those with one). Clicking a column header sorts
by that column's true values (dates sort as dates, not text). Approved (non-active) plans are hidden by
default (one click to bring back, count stated on the page). The table
collapses to the top 20 rows of the visible set with a show-more control;
client-side filters (status, inside/partial, date range, free text,
objection-open, show-approved) always operate over all rows.
Dates display as DD.MM.YYYY; ISO values stay in data-* attributes so all
sorting/filtering uses true dates. Statistics render in a collapsed block below the table; the footer (About) is last.
"""
import datetime
import html
import json
import urllib.parse as _urlparse_mod

from . import __version__

URGENT_DAYS = 30  # objection-window days for the urgent row (issue #153)
ACTIVE_STATUSES = ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")
DEPOSIT_MARK = "הפקדה"
COLLAPSE_TOP = 20

_CSS = """body{font-family:system-ui,Arial;max-width:1100px;margin:1em auto;padding:0 1em;background:#f3f6ff;color:#1f2937}
h1{color:#101f5b;border-right:6px solid #51b89a;padding-right:12px}
h2{color:#101f5b}
a{color:#00a8cf}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(16,31,91,.08)}
td,th{border:1px solid #dde4f6;padding:4px 8px;font-size:14px}
th{background:#101f5b;color:#fff;position:sticky;top:0}
th button{background:none;border:0;font:inherit;color:inherit;cursor:pointer;padding:0}
th button.sorted-asc::after{content:" ▲"}th button.sorted-desc::after{content:" ▼"}
tbody tr:nth-child(even){background:#f3f6ff}
.chip{border-radius:8px;padding:1px 8px;background:#dde4f6;color:#101f5b;white-space:nowrap}
.chip.c-deposit{background:#e8c31d;color:#1f2937}.chip.c-review{background:#00a8cf;color:#fff}
.chip.c-cond{background:#c8a4de;color:#1f2937}.chip.c-decision{background:#ff8c00;color:#1f2937}
.chip.c-inproc{background:#51b89a;color:#fff}.chip.c-approved{background:#6db633;color:#fff}
.chip.c-closed{background:#ececec;color:#777;text-decoration:line-through}
.legend{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px;margin:4px 0 8px}
.legend .chip{cursor:pointer}
.legend .chip.sel{outline:2px solid #101f5b;outline-offset:1px}
.derived{color:#666}.new td{background:#fdf3d7}
#filters,#pfilters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 8px;
padding:10px;border:1px solid #dde4f6;border-radius:10px;background:#fff;box-shadow:0 1px 3px rgba(16,31,91,.08)}
#filters input[type=search],#pfilters input[type=search]{flex:1;min-width:180px}
#fcount{font-size:12px;color:#555}
#more,#freset,#pfreset{background:#51b89a;color:#fff;border:0;border-radius:8px;cursor:pointer}
#more{margin:6px 0;padding:8px 16px}
#freset,#pfreset{padding:6px 12px}
tr.filtered-out{display:none}
#urgent-list{background:#fff;border:1px solid #dde4f6;border-right:4px solid #e61b2e;border-radius:10px;padding:10px 14px;list-style:none;margin:0}
#changes-list{background:#fff;border:1px solid #dde4f6;border-right:4px solid #51b89a;border-radius:10px;padding:10px 14px;list-style:none;margin:0}
#changes-list li{margin:4px 0}
.ai-banner{background:#fff;border:1px solid #dde4f6;border-right:4px solid #c8a4de;border-radius:10px;padding:10px 14px;margin:0 0 14px}
.review-body{background:#fff;border:1px solid #dde4f6;border-radius:10px;padding:14px 18px;max-width:900px}
.review-body h1{font-size:22px}.review-body h2{font-size:18px;margin-top:18px}.review-body h3{font-size:16px}
.review-body li{margin:4px 0}
.external-reviews{max-width:900px;margin:14px 0;border:1px dashed #9aa6c8;border-radius:10px;padding:8px 14px;background:#f7f8fc}
.external-reviews summary{cursor:pointer;font-weight:600}.ext-note,.ext-meta{color:#5a6485;font-size:13px}
#urgent-list li{margin:4px 0}
#datasets-list li{margin:4px 0}
footer{margin-top:24px;padding-top:10px;border-top:1px solid #dde4f6;font-size:13px;color:#555}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:1em}
.stats>div{background:#fff;border:1px solid #dde4f6;border-radius:10px;padding:10px}
.bars .bar{display:flex;align-items:center;gap:6px;margin:2px 0}
.bars .bl{flex:0 0 10em;overflow-wrap:anywhere}.bars .bt{display:block;flex:1;min-width:30px;height:14px;background:#e1e7ed;border-radius:4px;overflow:hidden}.bars .bf{display:block;height:100%;background:#101f5b;border-radius:4px}.bars .bv{flex:0 0 3ch;text-align:left;font-variant-numeric:tabular-nums}

@media (max-width:700px){
body{margin:.5em auto;padding:0 .75em;font-size:16px;line-height:1.45}
h1{font-size:22px;line-height:1.3}h2{font-size:19px}
body>p{font-size:14px}
#filters,#pfilters{flex-direction:column;align-items:stretch;gap:10px}
#filters input,#filters select,#filters button,#pfilters input,#pfilters select,#pfilters button{
font-size:16px;min-height:44px;width:100%;box-sizing:border-box}
#filters label,#pfilters label{display:flex;align-items:center;gap:10px;min-height:44px;font-size:16px}
#filters input[type=checkbox],#pfilters input[type=checkbox]{width:24px;min-height:24px;height:24px}
#more{width:100%;min-height:44px;font-size:16px}
.legend .chip{padding:8px 12px;font-size:14px}
#plans,#plans tbody,#plans tr,#plans td,#permits-table,#permits-table tbody,#permits-table tr,#permits-table td{display:block;width:auto}
#plans thead tr{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
#plans thead th{display:block;background:#fff;border:1px solid #51b89a;border-radius:16px;padding:0;position:static;color:#101f5b}
#plans thead th button{color:#101f5b}
#plans thead th:nth-child(8){display:none}

#plans thead th button{min-height:44px;padding:0 14px;font-size:14px}
#permits-table thead{display:none}
#plans tr,#permits-table tr{border:1px solid #dde4f6;border-radius:10px;margin:0 0 10px;padding:6px 10px;background:#fff}
#plans td,#permits-table td{border:0;padding:3px 0;font-size:15px;display:flex;justify-content:space-between;align-items:baseline;gap:12px}
#plans td::before,#permits-table td::before{color:#666;font-size:13px;flex:none}
#plans td:nth-child(1){font-weight:600;font-size:17px}
#plans td:nth-child(2){font-size:16px;padding-bottom:6px}
#plans td:nth-child(3){padding-bottom:6px}
#plans td:nth-child(4)::before{content:"קליטה"}
#plans td:nth-child(5)::before{content:"הפקדה"}
#plans td:nth-child(6)::before{content:"אחרון להתנגדות (משוער)"}
#plans td:nth-child(7)::before{content:"שטח (דונם)"}
#plans td:nth-child(8)::before{content:"סקירת AI"}
#permits-table td:nth-child(1){font-weight:600}
#permits-table td:nth-child(2)::before{content:"כתובת"}
#permits-table td:nth-child(3)::before{content:"מהות"}
#permits-table td:nth-child(4)::before{content:"סוג"}
#permits-table td:nth-child(5)::before{content:"סטטוס"}
#permits-table td:nth-child(6)::before{content:"תאריך סטטוס"}
#permits-table td:nth-child(7)::before{content:"תחילת פרסום"}
#permits-table td:nth-child(8)::before{content:"סיום פרסום"}
tr.filtered-out{display:none!important}
.stats{grid-template-columns:1fr}.bars .bl{width:8em}
footer{font-size:14px;line-height:1.8}footer a{display:inline-block;min-height:32px}
}
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
    r.dataset.mapMatch=vis?'1':'0';
    r.classList.toggle('filtered-out',!vis);
  });
  more.style.display=n>20?'':'none';
  more.textContent=expanded?'הצג 20 הראשונות':'הצג את כל '+n+' התכניות';
  fcount.textContent='מציג '+Math.min(n,expanded?n:20)+' מתוך '+n;
  document.dispatchEvent(new Event('plans-filtered'));
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
document.querySelectorAll('.plan-legend .chip').forEach(function(c){
  c.addEventListener('click',function(){
    var st=c.getAttribute('data-status');
    fstatus.value=(fstatus.value===st)?'':st;
    document.querySelectorAll('.plan-legend .chip').forEach(function(x){
      x.classList.toggle('sel',x.getAttribute('data-status')===fstatus.value);
    });
    expanded=false;apply();
  });
});
resort();
var URGENT_DAYS=30;
function _todayIL(){
  var q=new URLSearchParams(location.search).get('today');
  if(q&&/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/.test(q))return q;
  try{return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Jerusalem'}).format(new Date());}
  catch(e){return new Date().toISOString().slice(0,10);}
}
function _esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function _renderUrgent(){
  var ul=document.getElementById('urgent-list');if(!ul)return;
  var t=_todayIL(),tms=Date.parse(t+'T00:00:00Z'),items=[];
  rows.forEach(function(r){
    var d=r.getAttribute('data-obj');if(!d)return;
    var dd=Math.round((Date.parse(d+'T00:00:00Z')-tms)/86400000);
    if(dd<0||dd>URGENT_DAYS)return;
    var a=r.querySelector('td a');
    items.push({dd:dd,href:a?a.getAttribute('href'):'',num:r.getAttribute('data-num')||'',
      name:(r.cells[1]?r.cells[1].textContent:''),d:d.split('-').reverse().join('.')});
  });
  items.sort(function(a,b){return a.dd-b.dd;});
  ul.innerHTML=items.length?items.map(function(it){
    return '<li><a href="'+_esc(it.href)+'">'+_esc(it.num)+'</a> '+_esc(it.name)+
           ' - \u05d0\u05d7\u05e8\u05d5\u05df \u05dc\u05d4\u05ea\u05e0\u05d2\u05d3\u05d5\u05ea (\u05de\u05e9\u05d5\u05e2\u05e8): '+it.d+'</li>';}).join(''):'<li>\u05d0\u05d9\u05df</li>';
}
_renderUrgent();
fetch('rows.html').then(function(r){if(!r.ok)throw new Error('http');return r.text();}).then(function(h){
  var tb=document.querySelector('#plans tbody');if(!tb)return;
  tb.innerHTML=h;
  rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  resort();_renderUrgent();
  window.__rowsLoaded=true;
}).catch(function(){window.__rowsFailed=true;});
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
    return f"""<details id="stats"><summary>סטטיסטיקה</summary>
<div class="stats">
<div><h3>לפי סטטוס</h3>{_bars(dict(by_status))}</div>
<div><h3>בתוך השטח / חפיפה חלקית</h3>{_bars(dict(by_flag), flag_he)}</div>
<div><h3>הפקדות לפי חודש (24 אחרונים)</h3>{_bars(deposits)}</div>
<div><h3>אישורים לפי שנה</h3>{_bars(approvals)}</div>
</div></details>"""




def _permit_status_class(status: str) -> str:
    """Colour class for a permit-request status (mirrors the plan chip palette)."""
    st = status or ""
    if "נסגרה" in st:
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


_PERMIT_TERMINAL_STATUSES = frozenset({
    "הבקשה נסגרה",
    "הופק-הוצא היתר בניה",
    "הופק היתר מוארך",
})


def _permit_tik_link(tik_num: str | None) -> str:
    """Link a permit request number to its file in the municipality's
    licensing data viewer (תיק רישוי בניה, SystemCode 26400046). Issue #96."""
    tik = (tik_num or "").strip()
    if not tik:
        return ""
    url = ("https://ykpubdata.jerusalem.muni.il/#/Details?TikNum="
           + _urlparse_mod.quote(tik, safe="")
           + "&SystemCode=26400046&Page=BakashalInfo")
    return f"<a href='{url}' target='_blank' rel='noopener'>{_e(tik)}</a>"


def _permits_section(permits: list[dict], rows_file: str | None = None) -> str:
    """Separate DRAFT-labeled permit-requests section (issue: permit feed).
    A permit request is NOT a deposited plan; the section is visually and
    textually distinct from the plans table. Terminal requests (closed /
    permit issued) are hidden by default - the planner can no longer act
    on them - and revealed by one checkbox. Dates render dd.mm.yy with the
    ISO value kept in data-iso for filtering."""
    if not permits:
        return ""
    rows = []
    for p in permits:
        status = p.get("status") or ""
        sug = p.get("sugbakasha") or ""
        active = "0" if status in _PERMIT_TERMINAL_STATUSES else "1"
        pub_iso = _iso(p.get("publication_start"))
        search = _e(" ".join([
            p.get("tik_num") or "", p.get("address") or "",
            p.get("mahut") or "", sug,
            f"גוש {p.get('gush')}" if p.get("gush") else "",
            f"חלקה {p.get('helka')}" if p.get("helka") else "",
        ]).lower())
        rows.append(
            f"<tr class='{('filtered-out' if active == '0' else '')}' data-active='{active}' data-status='{_e(status)}' data-sug='{_e(sug)}'"
            f" data-pub='{pub_iso}' data-search='{search}'>"
            f"<td>{_permit_tik_link(p.get('tik_num'))}</td>"
            f"<td>{_e(p.get('address') or '')}</td>"
            f"<td>{_e(p.get('mahut') or '')}</td>"
            f"<td>{_e(sug)}</td>"
            f"<td><span class=\"chip {_permit_status_class(status)}\">{_e(status)}</span></td>"
            f"<td>{_date_cell(p.get('status_date'))}</td>"
            f"<td>{_date_cell(p.get('publication_start'))}</td>"
            f"<td>{_date_cell(p.get('publication_end_planned'))}</td></tr>")
    if rows_file:  # full set loads client-side (#169); the page keeps only the top rows
        with open(rows_file, "w", encoding="utf-8") as fh:
            fh.write("".join(rows))
    body = "".join(rows[:COLLAPSE_TOP])
    n_terminal = sum(1 for p in permits if (p.get("status") or "") in _PERMIT_TERMINAL_STATUSES)
    statuses = sorted({(p.get("status") or "") for p in permits if p.get("status")})
    from collections import Counter as _PCounter
    _pcounts = _PCounter((p.get("status") or "") for p in permits)
    plegend_chips = " ".join(
        f'<span class="chip {_permit_status_class(v)}" data-status="{_e(v)}">{_e(v)} ({_pcounts[v]})</span>'
        for v in statuses)
    plegend = '<div class="legend"><b>מקרא סטטוסים:</b> ' + plegend_chips + "</div>"
    sugs = sorted({(p.get("sugbakasha") or "") for p in permits if p.get("sugbakasha")})
    status_opts = "<option value=''>כל הסטטוסים</option>" + "".join(
        f"<option value='{_e(v)}'>{_e(v)}</option>" for v in statuses)
    sug_opts = "<option value=''>כל הסוגים</option>" + "".join(
        f"<option value='{_e(v)}'>{_e(v)}</option>" for v in sugs)
    return f"""
<section id="permits" dir="rtl">
<h2>בקשות היתר (טיוטה - DRAFT)</h2>
<p class="permits-note">מקור: מערכת איתור הנתונים ברישוי של עיריית ירושלים.
בקשת היתר אינה תכנית מופקדת - ההתנגדות לבקשה מוגשת לפי הוראות הפרסום
(סעיף 149 לחוק התכנון והבניה) ובמועדים שבפרסום עצמו.
בקשות שהסתיימו (נסגרו או הופק היתר) מוסתרות כברירת מחדל.
מספר הבקשה מקשר לתיק במערכת
<a href='https://ykpubdata.jerusalem.muni.il/' target='_blank' rel='noopener'>איתור נתונים ברישוי של העירייה</a>.</p>
{plegend}
<div id="pfilters">
<input type="search" id="pfq" placeholder="חיפוש: מספר בקשה / כתובת / מהות / גוש / חלקה">
<select id="pfstatus">{status_opts}</select>
<select id="pfsug">{sug_opts}</select>
<label>מתאריך פרסום <input type="date" id="pffrom"></label>
<label>עד <input type="date" id="pfto"></label>
<label><input type="checkbox" id="pfclosed"> הצג בקשות שהסתיימו ({n_terminal})</label>
<button id="pfreset" type="button">נקה</button>
<span id="pfcount"></span>
</div>
<table id="permits-table"><thead><tr>
<th>מספר בקשה</th><th>כתובת</th><th>מהות</th><th>סוג</th><th>סטטוס</th>
<th>תאריך סטטוס</th><th>תחילת פרסום</th><th>סיום פרסום (מתוכנן)</th>
</tr></thead><tbody>{body}</tbody></table>
<noscript><p>מוצגות {COLLAPSE_TOP} הבקשות הראשונות בלבד - להצגת כולן ולהשתמש בסינון יש להפעיל JavaScript.</p></noscript>
<button id="pmore" type="button"></button>
</section>"""

_PERMITS_JS = """
(function(){
var rows=Array.prototype.slice.call(document.querySelectorAll('#permits-table tbody tr'));
if(!rows.length){window.__permitsLoaded=true;return;}
var pfq=document.getElementById('pfq'),pfstatus=document.getElementById('pfstatus'),
pfsug=document.getElementById('pfsug'),pffrom=document.getElementById('pffrom'),
pfto=document.getElementById('pfto'),pfclosed=document.getElementById('pfclosed'),
pfcount=document.getElementById('pfcount'),pmore=document.getElementById('pmore');
var expanded=false;
function match(r){
  if(!pfclosed.checked&&!pfstatus.value&&r.getAttribute('data-active')!=='1')return false;
  var q=pfq.value.trim().toLowerCase();
  if(q&&r.getAttribute('data-search').indexOf(q)===-1)return false;
  if(pfstatus.value&&r.getAttribute('data-status')!==pfstatus.value)return false;
  if(pfsug.value&&r.getAttribute('data-sug')!==pfsug.value)return false;
  var pub=r.getAttribute('data-pub');
  if(pffrom.value&&!(pub&&pub>=pffrom.value))return false;
  if(pfto.value&&!(pub&&pub<=pfto.value))return false;
  return true;
}
function apply(){
  var n=0;
  rows.forEach(function(r){
    var vis=match(r);
    if(vis){n++;if(!expanded&&n>20)vis=false;}
    r.classList.toggle('filtered-out',!vis);
  });
  pmore.style.display=n>20?'':'none';
  pmore.textContent=expanded?'הצג 20 הראשונות':'הצג את כל '+n+' הבקשות';
  pfcount.textContent='מציג '+Math.min(n,expanded?n:20)+' מתוך '+n;
}
[pfq,pfstatus,pfsug,pffrom,pfto,pfclosed].forEach(function(el){
  var h=function(){expanded=false;apply();};
  el.addEventListener('input',h);el.addEventListener('change',h);
});
document.getElementById('pfreset').addEventListener('click',function(){
  pfq.value='';pfstatus.value='';pfsug.value='';pffrom.value='';pfto.value='';
  pfclosed.checked=false;expanded=false;apply();
});
pmore.addEventListener('click',function(){expanded=!expanded;apply();});
fetch('permits.html').then(function(r){if(!r.ok)throw new Error('http');return r.text();}).then(function(h){
  var tb=document.querySelector('#permits-table tbody');if(!tb)return;
  tb.innerHTML=h;
  rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  apply();
  window.__permitsLoaded=true;
}).catch(function(){window.__permitsFailed=true;});
document.querySelectorAll('#permits .legend .chip').forEach(function(c){
  c.addEventListener('click',function(){
    var st=c.getAttribute('data-status');
    pfstatus.value=(pfstatus.value===st)?'':st;
    document.querySelectorAll('#permits .legend .chip').forEach(function(x){
      x.classList.toggle('sel',x.getAttribute('data-status')===pfstatus.value);
    });
    expanded=false;apply();
  });
});
apply();
})();
"""

def _social_meta(council_name: str, base_url: str, preview_image: bool) -> str:
    """Open Graph + Twitter card tags. The image URL must be absolute, so the
    image tags appear only with a base_url and a generated og.png."""
    title = f"תכניות תכנון ובנייה - {council_name}"
    desc = "תכניות והיתרים באזור: סטטוס, מועדי הפקדה ותאריך אחרון להתנגדות (משוער)."
    tags = [("name", "description", desc), ("property", "og:type", "website"),
            ("property", "og:locale", "he_IL"), ("property", "og:title", title),
            ("property", "og:description", desc)]
    if base_url:
        tags.append(("property", "og:url", base_url))
    if base_url and preview_image:
        tags += [("property", "og:image", base_url.rstrip("/") + "/og.png"),
                 ("property", "og:image:width", "1200"), ("property", "og:image:height", "630"),
                 ("property", "og:image:alt", title), ("name", "twitter:card", "summary_large_image"),
                 ("name", "twitter:image", base_url.rstrip("/") + "/og.png")]
    else:
        tags.append(("name", "twitter:card", "summary"))
    tags += [("name", "twitter:title", title), ("name", "twitter:description", desc)]
    return "\n".join(f'<meta {k}="{n}" content="{_e(v)}">' for k, n, v in tags)


def render_index(rows: list[dict], changes: list[dict], generated: str, council_name: str,
                 permits: list[dict] | None = None, base_url: str = "",
                 preview_image: bool = False, reviews: dict[str, str] | None = None,
                 rows_file: str | None = None, permits_file: str | None = None) -> str:
    reviews = reviews or {}
    from . import mapview
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
        return f'<span class="chip {cls}" data-status="{_e(st)}">{_e(st)}</span>'


    def review_cell(r):
        url = reviews.get(r["pl_number"])
        if not url:
            return "—"
        return (f"<a class='ai-review' href='{_e(url)}' "
                f"title='סיכום נקודות לדיון שהופק באמצעות AI - אינו מסמך רשמי'>סקירה</a>")

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
                f"<td>{_e(r['pl_area_dunam'])}</td><td>{review_cell(r)}</td></tr>")

    new_ids = {c["pl_number"] for c in changes if c["kind"] == "new"}
    for r in rows:
        r["_is_new"] = r["pl_number"] in new_ids
    if rows_file:  # full set loads client-side (#164); the page keeps only the top rows
        with open(rows_file, "w", encoding="utf-8") as fh:
            fh.write("\n".join(tr(r) for r in rows))
    body = "\n".join(tr(r) for r in rows[:COLLAPSE_TOP])
    stats_html = stats_section(rows)
    # Urgent = derived objection deadline within [0, URGENT_DAYS] of the
    # generation date; the browser recomputes the same window at page load
    # against "today" in Asia/Jerusalem, so the row stays current between
    # refreshes with no Action (issue #153).
    gen_d = datetime.date.fromisoformat(generated)

    def _urgent_window(r):
        iso = _iso(r["objection_deadline_derived_60d_from_publication"])
        if not iso:
            return False
        try:
            dd = (datetime.date.fromisoformat(iso) - gen_d).days
        except ValueError:
            return False
        return 0 <= dd <= URGENT_DAYS

    urgent = sorted((r for r in rows if _urgent_window(r)),
                    key=lambda r: _iso(r["objection_deadline_derived_60d_from_publication"]))
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
    legend = '<div class="legend plan-legend"><b>מקרא סטטוסים:</b> ' + " ".join(chip(s) for s in statuses) + "</div>"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>תכניות במינהל הקהילתי {_e(council_name)}</title>
<link rel="alternate" type="application/atom+xml" href="feed.xml">
{_social_meta(council_name, base_url, preview_image)}
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="style.css"><link rel="stylesheet" href="plan-map.css"></head><body>
<h1>תכניות תכנון ובנייה בשטח המינהל הקהילתי {_e(council_name)}</h1>
<p>עודכן: {_e(generated)}. מקור: שירות התכנון הציבורי (iplan) - נתונים משוערים, לצורכי מידע בלבד.</p>
<p><b>סדר ברירת המחדל:</b> לפי "אחרון להתנגדות" (משוער) - התאריך הרחוק ביותר למעלה;
תכניות ללא תאריך יעד להתנגדות מופיעות מתחת לאלה שיש להן. לחיצה על כותרת עמודה ממיינת לפיה.
מוצגות {COLLAPSE_TOP} התכניות הרלוונטיות ביותר; סינון וחיפוש פועלים על כל התכניות.
תכניות מאושרות ({n_approved}) מוסתרות כברירת מחדל - סמנו "הצג תכניות מאושרות" כדי לראותן.</p>
<p>עמודת "אחרון להתנגדות" היא <b>הערכה מחושבת</b> (פרסום הפקדה + 60 יום) - לבדיקה מול המו"ת.</p>
<p>עמודת "סקירת AI" מקשרת לסיכומי נקודות לדיון שהופקו <b>אוטומטית באמצעות AI</b> מתוך מסמכי התכנית - התוכן אינו מסמך רשמי ואינו תחליף לקריאת המסמכים במו"ת.</p>
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
<th title="סיכום שהופק באמצעות AI - אינו מסמך רשמי">סקירת AI</th></tr></thead>
<tbody>{body}</tbody></table>
<noscript><p>מוצגות {COLLAPSE_TOP} התכניות המובילות בלבד - להצגת כל התכניות ולהשתמש בסינון יש להפעיל JavaScript.</p></noscript>
<button id="more" type="button">הצג את כל {len(rows)} התכניות</button>
{_permits_section(permits or [], rows_file=permits_file)}
{mapview.PANEL}
<h2>דחוף להתנגדות</h2><ul id="urgent-list">{urgent_html}</ul>
<h2>שינויים אחרונים</h2><ul id="changes-list">{changes_html}</ul>
{stats_html}
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת גינות העיר. קוד מקור ונתונים:
<a href="https://github.com/reihlinstinct/ginot-hair-plans">GitHub</a>
&middot; <a href="about.html">אודות ומקורות נתונים</a>
&middot; <a href="https://github.com/reihlinstinct/ginot-hair-plans/blob/main/CONTRIBUTING.md">איך לתרום</a>
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
<script>{_JS}{_PERMITS_JS}</script>
</body></html>"""


_SOURCES_ROWS = [
    ("תכניות במינהל", "שירות התכנון הציבורי (iplan), מנהל התכנון",
     "מספר ושם התכנית, סטטוס, תאריכי קליטה והפקדה, שטח; מועד אחרון להתנגדות מחושב (הערכה)",
     "רענון שבועי (יום שלישי) ורענונים ידניים",
     '<a href="data.json">data.json</a>'),
    ("פרסומי הפקדה", "land.gov.il - מינהל מקרקעי ישראל",
     "תאריכי פרסום ההפקדה בעיתונים וביתרונות לכל תכנית",
     "רענון שבועי",
     '<a href="https://land.gov.il">land.gov.il</a>'),
    ("בקשות היתר", "איתור נתונים ברישוי, עיריית ירושלים",
     "מספר בקשה, כתובת, מהות, סוג, סטטוס, תאריכי סטטוס ופרסום, גוש וחלקה",
     "סריקת חלקות באצוות ליליות (בשלבי השלמה ראשונית) והעשרת סטטוסים",
     '<a href="https://ykpubdata.jerusalem.muni.il/">איתור נתונים ברישוי</a>'),
    ("מסמכי תכנית וסקירות AI", 'מאב"ת - מערכת איתור בינוי ותכניות',
     "מסמכי הוראות, תשריט והודעות; סיכומי נקודות לדיון שהופקו באמצעות AI (מסומנים, אינם מסמך רשמי)",
     "לפי צורך, לתכניות נבחרות",
     '<a href="https://mavat.iplan.gov.il/">מאב"ת</a>'),
    ("גבול המינהל", "קובץ גבול גיאוגרפי במאגר",
     "פוליגון שטח המינהל הקהילתי (geojson)",
     "עדכון ידני בשינוי גבול",
     '<a href="https://github.com/reihlinstinct/ginot-hair-plans/tree/main/data">תיקיית data</a>'),
]

_SOURCES_REDIRECT = """<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=about.html">
<title>מקורות נתונים</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022"></head>
<body><p>העמוד עבר: <a href="about.html">אודות ומקורות נתונים</a></p></body></html>
"""

_DATASETS_JS = """
fetch('index.json').then(function(r){if(!r.ok)throw new Error('http');return r.json();}).then(function(ix){
  var ul=document.getElementById('datasets-list');if(!ul)return;
  ul.innerHTML=(ix.datasets||[]).map(function(d){
    return '<li><a href="'+String(d.url).replace(/&/g,'&amp;').replace(/</g,'&lt;')+'">'+String(d.name).replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</a>'+
      (d.records!=null?' - '+d.records+' \u05e8\u05e9\u05d5\u05de\u05d5\u05ea':'')+'</li>';
  }).join('')||'<li>\u05d0\u05d9\u05df</li>';
}).catch(function(){
  var ul=document.getElementById('datasets-list');
  if(ul)ul.innerHTML='<li>\u05e8\u05e9\u05d9\u05de\u05ea \u05de\u05e2\u05e8\u05db\u05d9 \u05d4\u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05dc\u05d0 \u05d6\u05de\u05d9\u05e0\u05d4 \u05db\u05e8\u05d2\u05e2</li>';
});
"""


def render_about(generated: str, council_name: str) -> str:
    """Combined About + data-sources + datasets page (issue: datasets off the
    main page, owner request 2026-10-21). Generated with the site so the
    update stamp stays current; the datasets list loads from index.json."""
    rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(src)}</td><td>{_e(what)}</td>"
        f"<td>{_e(cad)}</td><td>{link}</td></tr>"
        for name, src, what, cad, link in _SOURCES_ROWS)
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>אודות ומקורות נתונים - {_e(council_name)}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="style.css"></head><body>
<h1>אודות האתר</h1>
<p>אתר זה מרכז מידע ציבורי על תכניות ובקשות היתר הרלוונטיים לשטחי ועדת
<strong>גינות העיר</strong> בירושלים, ומתעדכן אוטומטית. עודכן: {_e(generated)}.</p>
<div class="ai-banner">האתר הוא <strong>יוזמה עצמאית של הוועד</strong> ואינו אתר רשמי של עיריית
ירושלים, מנהל התכנון או רשות מקרקעי ישראל. המידע באתר הוא לנוחות בלבד,
אינו תחליף למקורות הרשמיים ואינו ייעוץ משפטי. מועדי התנגדות המוצגים הם
הערכה בלבד - המועד המחייב נקבע לפי הודעות ההפקדה הרשמיות.</div>
<h2>מקורות נתונים</h2>
<table id="plans"><thead><tr><th>מערך נתונים</th><th>מקור</th><th>מה נאסף</th><th>תדירות עדכון</th><th>קישורים</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>מערכי נתונים</h2>
<ul id="datasets-list"><li>טוען רשימה...</li></ul>
<h2>גישה לנתונים (API)</h2>
<p>הנתונים זמינים כקבצים סטטיים (JSON / Atom) לשימוש חופשי, עם CORS פתוח.
אין שאילתות צד-שרת - הסינון מתבצע אצל הלקוח. כל הקבצים מתעדכנים בכל רענון
של האתר (רענון שבועי ורענונים ידניים).</p>
<table id="plans"><thead><tr><th>קובץ</th><th>תוכן</th><th>מבנה</th></tr></thead><tbody>
<tr><td><a href="data.json">data.json</a></td><td>מערך הנתונים המלא: תכניות, שינויים אחרונים ובקשות היתר</td>
<td>{{generated, rows[], changes[], permits[]}} - שמות השדות כפי שהגיעו מ-iplan / איתור הנתונים ברישוי</td></tr>
<tr><td><a href="open.json">open.json</a></td><td>תכניות פתוחות בלבד (עדיין בתהליך תכנוני)</td>
<td>{{generated, definition, count, plans[]}} - כל רשומה כוללת in_objection_period (חלון התנגדויות פתוח היום)</td></tr>
<tr><td><a href="feed.xml">feed.xml</a></td><td>פיד Atom של תכניות חדשות ושינויים</td><td>Atom 1.0</td></tr>
<tr><td><a href="badge/plans.json">badge/*.json</a></td><td>נקודות קצה לתגי shields.io (מספר תכניות, פירוט סטטוסים, תאריך עדכון)</td>
<td>{{schemaVersion, label, message, color}}</td></tr>
<tr><td><a href="https://ginot-hair-api.reihlinstinct.workers.dev">ginot-hair-api.reihlinstinct.workers.dev</a></td>
<td>שכבת שאילתות לקריאה בלבד (Cloudflare Worker): /plans?open=1&status=&q=&before=YYYY-MM-DD&limit=, /permits?street=&status=&type=&q=&limit=, /open, /status</td>
<td>JSON; מטמון קצה 5 דקות; הגבלת קצב 120 בקשות לדקה (best-effort)</td></tr>
</tbody></table>
<h2>פרטיות</h2>
<p>האתר מציג נתונים ממקורות ציבוריים בלבד. שדות המזהים בעלי עניין פרטיים
(למשל בעלי עניין בבקשות היתר) מוסרים בצינור העיבוד ואינם מוצגים כאן,
אף שהם גלויים במקור.</p>
<h2>קוד ונתונים</h2>
<p>קוד האתר והנתונים המעובדים פתוחים:
<a href="https://github.com/reihlinstinct/ginot-hair-plans">GitHub</a>.
רוצים לעזור? <a href="https://github.com/reihlinstinct/ginot-hair-plans/blob/main/CONTRIBUTING.md">איך לתרום</a>.</p>
<p><a href="index.html">חזרה לעמוד הראשי</a></p>
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת {_e(council_name)} - בלתי רשמי.
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
<script>{_DATASETS_JS}</script>
</body></html>"""


def review_social_meta(pl_number, plan_name, base_url, has_image):
    title = f"סקירת AI - {pl_number}" + (f" | {plan_name}" if plan_name else "")
    desc = "נקודות לדיון מתוך מסמכי התכנית. סיכום אוטומטי, לא מסמך רשמי ולא ייעוץ מקצועי."
    tags = [("property", "og:type", "article"), ("property", "og:locale", "he_IL"),
            ("property", "og:title", title), ("property", "og:description", desc),
            ("name", "description", desc), ("name", "twitter:title", title),
            ("name", "twitter:description", desc)]
    if base_url:
        base = base_url.rstrip("/") + "/"
        tags.append(("property", "og:url", base + f"reviews/talking_points_{pl_number}.html"))
        image = base + (f"reviews/og_{pl_number}.png" if has_image else "og.png")
        tags += [("property", "og:image", image), ("property", "og:image:width", "1200"),
                 ("property", "og:image:height", "630"), ("property", "og:image:type", "image/png"),
                 ("property", "og:image:alt", title), ("name", "twitter:image", image),
                 ("name", "twitter:card", "summary_large_image")]
    else:
        tags.append(("name", "twitter:card", "summary"))
    return "\n".join(f'<meta {key}="{name}" content="{_e(value)}">' for key, name, value in tags)


def render_review(pl_number: str, md_text: str, generated: str, council_name: str,
                  base_url: str = "", plan_name: str = "", preview_image: bool = False,
                  external_html: str = "") -> str:
    """Render a plan's AI talking-points markdown as a styled site page
    (issue #177). The .md stays the source of truth in the repo; the site
    render converts it - no separate Action. Clearly labelled AI content."""
    import markdown
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    social = review_social_meta(pl_number, plan_name, base_url, preview_image)
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>סקירת AI - תכנית {_e(pl_number)}</title>
{social}
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="../favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="../favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="../favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="../apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="../style.css"></head><body>
<div class="ai-banner"><b>סקירת AI</b> - סיכום נקודות לדיון שהופק <b>אוטומטית באמצעות AI</b>
מתוך מסמכי התכנית הרשמיים. התוכן אינו מסמך רשמי ואינו תחליף לקריאתם במו"ת.</div>
<article class="review-body">
{body}
</article>
{external_html}
<p><a href="../index.html">חזרה לעמוד הראשי</a> &middot; עודכן: {_e(generated)}</p>
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת {_e(council_name)} - בלתי רשמי.
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
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
                permits_path: str | None = None, council_geojson: str | None = None,
                plans_dir: str = "plans",
                external_reviews_path: str = "data/external_reviews.json"):
    import glob
    import os
    import re as _re
    import shutil
    os.makedirs(out_dir, exist_ok=True)
    from pathlib import Path
    static = Path(__file__).parent / "static"
    shutil.copytree(static, out_dir, dirs_exist_ok=True)
    reviews = {}
    review_pages = {}
    for path in sorted(glob.glob(os.path.join(plans_dir, "*", "analysis", "talking_points_*.md"))):
        m = _re.fullmatch(r"talking_points_(\d+-\d+)\.md", os.path.basename(path))
        if m:
            reviews[m.group(1)] = f"reviews/talking_points_{m.group(1)}.html"
            with open(path, encoding="utf-8") as rf:
                review_pages[m.group(1)] = rf.read()
    generated = datetime.date.today().isoformat()
    permits = []
    if permits_path:
        try:
            with open(permits_path, encoding="utf-8") as pf:
                permits = json.load(pf).get("requests", [])
        except (FileNotFoundError, json.JSONDecodeError):
            permits = []
    from . import preview
    sort_rows(rows)  # annotates _open_obj, which the preview card counts
    has_img = preview.render_preview(rows, council_name, generated, "data/council_ginot_hair.geojson"
                                     if os.path.exists("data/council_ginot_hair.geojson")
                                     else "data/council.geojson", f"{out_dir}/og.png")
    with open(f"{out_dir}/style.css", "w", encoding="utf-8") as fh:
        fh.write(_CSS)
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as fh:
        fh.write(render_index(rows, changes, generated, council_name, permits,
                              base_url=base_url, preview_image=has_img, reviews=reviews,
                              rows_file=f"{out_dir}/rows.html",
                              permits_file=f"{out_dir}/permits.html"))
    from . import external_reviews as _er
    external = _er.load(external_reviews_path)
    if _er.validate_entries(external):
        external = []  # never render an invalid file
    if review_pages:
        os.makedirs(f"{out_dir}/reviews", exist_ok=True)
        row_by_number = {r.get("pl_number"): r for r in rows}
        for pl, md_text in review_pages.items():
            row = row_by_number.get(pl, {"pl_number": pl})
            review_image = preview.render_review_preview(row, generated, f"{out_dir}/reviews/og_{pl}.png")
            with open(f"{out_dir}/reviews/talking_points_{pl}.html", "w", encoding="utf-8") as fh:
                fh.write(render_review(pl, md_text, generated, council_name, base_url,
                                       row.get("pl_name") or "", review_image,
                                       _er.render_section(external, pl)))
    with open(f"{out_dir}/about.html", "w", encoding="utf-8") as fh:
        fh.write(render_about(generated, council_name))
    with open(f"{out_dir}/sources.html", "w", encoding="utf-8") as fh:
        fh.write(_SOURCES_REDIRECT)
    with open(f"{out_dir}/feed.xml", "w", encoding="utf-8") as fh:
        fh.write(render_feed(changes, generated, council_name, base_url))
    with open(f"{out_dir}/data.json", "w", encoding="utf-8") as fh:
        json.dump({"generated": generated, "rows": rows, "changes": changes,
                   "permits": permits}, fh, ensure_ascii=False)
    # Public "open plans" endpoint (owner request 2026-10-21): plans still in
    # the planning process (definition A: station_desc is not "אישור"), with a
    # public flag for an open objection window. sort_rows above already
    # annotated _open_obj for every row.
    open_rows = []
    for r in rows:
        if _is_active(r):
            rr = dict(r)
            rr["in_objection_period"] = bool(r.get("_open_obj"))
            open_rows.append(rr)
    with open(f"{out_dir}/open.json", "w", encoding="utf-8") as fh:
        json.dump({"generated": generated,
                   "definition": "station_desc != 'אישור' - תכניות שעדיין בתהליך תכנוני",
                   "count": len(open_rows), "plans": open_rows},
                  fh, ensure_ascii=False)
