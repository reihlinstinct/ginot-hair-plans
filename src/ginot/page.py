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
import json

from . import __version__
from .dates import today_il
from .page_permit_policy import (  # noqa: F401 - keep the page module API
    _PERMIT_GROUP_CLASS,
    _PERMIT_PUB_EVIDENCE_STATUSES,
    _PERMIT_SCOPE_IN,
    _PERMIT_SCOPE_OUT,
    _PERMIT_TERMINAL_STATUSES,
    COMMUNITY_SOURCE_CASES,
    COMMUNITY_SOURCE_RECORDS,
    COMMUNITY_SOURCE_URL,
    PERMIT_AI_REVIEWS,
    PERMIT_ID_RE,
    PERMIT_STATUS_GROUPS,
    _community_source_link,
    _is_default_permit_candidate,
    _permit_review_cell,
    _permit_scope,
    _permit_status_class,
    _permit_status_group,
    _permit_tik_link,
    publication_evidence_tiks,
    write_permit_ids,
)
from .page_permits import _permits_section
from .page_resources import (  # noqa: F401 - keep the page module API
    _ANALYTICS_SNIPPET,
    _CSS,
    _DATASETS_JS,
    _SOURCES_REDIRECT,
    _SOURCES_ROWS,
    COLLAPSE_TOP,
    _date_cell,
    _e,
    _fmt,
    _iso,
)
from .page_secondary import (  # noqa: F401 - keep the page module API
    render_about,
    render_feed,
    render_review,
    review_social_meta,
)
from .public_api import project as public_project

# Section: Main table controls and search

URGENT_DAYS = 30  # objection-window days for the urgent row (issue #153)
ACTIVE_STATUSES = ("הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך")
DEPOSIT_MARK = "הפקדה"
# Shared search folding for the plans (#fq) and permits (#pfq) tables, applied
# identically to the query and to each row's data-search text (#413, #468).
# Lowercases; drops niqqud/cantillation (U+0591-U+05C7, which includes maqaf),
# geresh/gershayim, ASCII and typographic quotes/primes, hyphens and dashes,
# and invisible bidi/zero-width marks; then collapses whitespace (NBSP included)
# to one space. No aliases: only spelling variants of the same text match.
_NORM_SEARCH_JS = r"""function normSearch(s){
  return (s||'').toLowerCase()
    .replace(/[\u0591-\u05C7\u05F3\u05F4\u00B4\u02B9\u02BC\u2010-\u2015\u2018-\u201F\u2032\u2033\u2212'"`-]/g,'')
    .replace(/[\u200B-\u200F\u202A-\u202E\u2066-\u2069]/g,'')
    .replace(/\s+/g,' ').trim();
}
function searchMatches(text, query){
  var raw=(query||'').trim();
  if(!normSearch(raw)&&raw.indexOf('|')===-1)return true;
  var terms=raw.split('|').map(normSearch).filter(function(t){return t.length>0;});
  return terms.some(function(term){return text.indexOf(term)!==-1;});
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
{_NORM_SEARCH_JS}function match(r){
  if(!fappr.checked&&r.getAttribute('data-active')!=='1')return false;
  if(!searchMatches(r.__ns||(r.__ns=normSearch(r.getAttribute('data-search'))),fq.value))return false;
  if(fstatus.value&&r.getAttribute('data-status')!==fstatus.value)return false;
  if(fflag.value&&r.getAttribute('data-flag')!==fflag.value)return false;
  if(fobj.checked&&r.getAttribute('data-open')!=='1')return false;
  var a=r.getAttribute('data-recv'),b=r.getAttribute('data-dep');
  if(ffrom.value&&!((a&&a>=ffrom.value)||(b&&b>=ffrom.value)))return false;
  if(fto.value&&!((a&&a<=fto.value)||(b&&b<=fto.value)))return false;
  return true;
}
function apply(){
  document.querySelectorAll('.plan-legend .chip').forEach(function(c){
    c.classList.toggle('sel',c.getAttribute('data-status')===fstatus.value);
  });
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
var planLink=window.GinotFilterLinks.register('plan',
  {fq:1,fstatus:1,fflag:1,fobj:1,ffrom:1,fto:1,fappr:1}, {
  keys:['expanded','sort','dir'],
  restore:function(p,n){
    if(p.get(n+'.expanded')==='1')expanded=true;
    var k=p.get(n+'.sort'),d=p.get(n+'.dir');
    if(['num','name','status','recv','dep','obj','area'].indexOf(k)!==-1)sortKey=k;
    if(d==='1'||d==='-1')sortDir=Number(d);
  },
  write:function(p,n){
    if(expanded)p.set(n+'.expanded','1');
    if(sortKey!=='obj')p.set(n+'.sort',sortKey);
    if(sortDir!==-1)p.set(n+'.dir',String(sortDir));
  }
});
planLink.restore();resort();
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
  document.querySelectorAll('#permits-table tbody tr').forEach(function(r){
    var group=r.getAttribute('data-group');
    if((group!=='obj'&&group!=='pubcheck')||r.getAttribute('data-scope')==='out')return;
    var a=r.querySelector('td a'),num=a?a.textContent.trim():'';
    function validDeadline(value){
      if(!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value||''))return false;
      var ms=Date.parse(value+'T00:00:00Z');
      return isFinite(ms)&&new Date(ms).toISOString().slice(0,10)===value;
    }
    var candidate=(window.__permitOfficialDeadlines||{})[num];
    var official=validDeadline(candidate)?candidate:'';
    if(group==='pubcheck'&&!official)return;
    var planned=r.getAttribute('data-pubend');
    var d=official||(validDeadline(planned)?planned:'');if(!d)return;
    var parsed=Date.parse(d+'T00:00:00Z');
    if(!isFinite(parsed)||new Date(parsed).toISOString().slice(0,10)!==d)return;
    var dd=Math.round((parsed-tms)/86400000);if(dd<0||dd>URGENT_DAYS)return;
    items.push({dd:dd,href:a?a.getAttribute('href'):'',num:num,
      name:'בקשת היתר: '+(r.cells[1]?r.cells[1].textContent:''),
      d:d.split('-').reverse().join('.'),permit:true,official:!!official,verify:group==='pubcheck'});
  });
  items.sort(function(a,b){return a.dd-b.dd;});
  ul.innerHTML=items.length?items.map(function(it){
    return '<li><a href="'+_esc(it.href)+'">'+_esc(it.num)+'</a> '+_esc(it.name)+
           ' - '+(it.permit?(it.verify?'פרסום עירוני - דורש בדיקה; אפשרות הגשה לא אומתה. מועד בפרסום: ':it.official?'מועד התנגדות (פרסום עירוני): ':'סיום פרסום מתוכנן (לא מאומת): '):'אחרון להתנגדות (משוער): ')+it.d+'</li>';}).join(''):'<li>\u05d0\u05d9\u05df</li>';
}
window.__renderUrgent=_renderUrgent;
_renderUrgent();
fetch('publications_active.json').then(function(r){if(!r.ok)throw new Error('unavailable');return r.json();}).then(function(list){
  var deadlines={};
  list.forEach(function(r){
    if(r.in_polygon===true&&r.objection_deadline)deadlines[r.tik_num]=r.objection_deadline;
  });
  window.__permitOfficialDeadlines=deadlines;_renderUrgent();
}).catch(function(){/* Planned dates remain clearly labelled, never upgraded. */});
fetch('rows.html').then(function(r){if(!r.ok)throw new Error('http');return r.text();}).then(function(h){
  var tb=document.querySelector('#plans tbody');if(!tb)return;
  tb.innerHTML=h;
  rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  resort();_renderUrgent();
  window.__rowsLoaded=true;
}).catch(function(){window.__rowsFailed=true;});
})();
""".replace("{_NORM_SEARCH_JS}", _NORM_SEARCH_JS)


# Section: Plan formatting and statistics


def _deposit_date(r) -> str:
    return r.get("pl_last_deposit_date") or r.get("depositing_date") or ""


def _is_open_objection(r, today: str) -> bool:
    st = r.get("station_desc") or ""
    deadline = _iso(r.get("objection_deadline_derived_2m_from_publication"))
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
    today = today or today_il().isoformat()
    for r in rows:
        r["_open_obj"] = _is_open_objection(r, today)
    with_dl = sorted(
        (
            r
            for r in rows
            if _iso(r.get("objection_deadline_derived_2m_from_publication"))
        ),
        key=lambda r: _iso(r.get("objection_deadline_derived_2m_from_publication")),
        reverse=True,
    )
    without_dl = sorted(
        (
            r
            for r in rows
            if not _iso(r.get("objection_deadline_derived_2m_from_publication"))
        ),
        key=lambda r: _iso(r.get("receiving_date")),
        reverse=True,
    )
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
        out.append(
            f"<div class='bar'><span class='bl'>{_e(label)}</span>"
            f"<span class='bt'><span class='bf' style='width:{pct}%'></span></span>"
            f"<span class='bv'>{v}</span></div>"
        )
    return "<div class='bars'>" + "".join(out) + "</div>"


def _month_key(iso: str) -> str:
    return iso[:7] if iso and len(iso) >= 7 else ""


def stats_section(rows: list[dict]) -> str:
    from collections import Counter

    by_status = Counter(r.get("station_desc") or "(ללא)" for r in rows)
    by_flag = Counter(r.get("inside_flag") or "(ללא)" for r in rows)
    deposits = Counter(
        filter(
            None,
            (
                _month_key(
                    r.get("pl_last_deposit_date") or r.get("depositing_date") or ""
                )
                for r in rows
            ),
        )
    )
    deposits_by_month = dict(sorted(deposits.items())[-24:])
    approvals = Counter(
        filter(None, ((r.get("pl_date_8_approval") or "")[:4] for r in rows))
    )
    approvals_by_year = dict(sorted(approvals.items()))
    flag_he = {"inside": "בתוך השטח", "partial": "חפיפה חלקית"}
    return f"""<details id="stats"><summary>סטטיסטיקה</summary>
<div class="stats">
<div><h3>לפי סטטוס</h3>{_bars(dict(by_status))}</div>
<div><h3>בתוך השטח / חפיפה חלקית</h3>{_bars(dict(by_flag), flag_he)}</div>
<div><h3>הפקדות לפי חודש (24 אחרונים)</h3>{_bars(deposits_by_month)}</div>
<div><h3>אישורים לפי שנה</h3>{_bars(approvals_by_year)}</div>
</div></details>"""


# Section: Permit browser controller

_PERMITS_JS = """
(function(){
var rows=Array.prototype.slice.call(document.querySelectorAll('#permits-table tbody tr'));
if(!rows.length){window.__permitsLoaded=true;return;}
var pfq=document.getElementById('pfq'),pfstatus=document.getElementById('pfstatus'),
pfsug=document.getElementById('pfsug'),pffrom=document.getElementById('pffrom'),
pfto=document.getElementById('pfto'),pfclosed=document.getElementById('pfclosed'),
pfopenonly=document.getElementById('pfopenonly'),pfscope=document.getElementById('pfscope'),
pfgroups=document.getElementById('pfgroups'),
pfcount=document.getElementById('pfcount'),pmore=document.getElementById('pmore'),
pfunknown=document.getElementById('pfunknown'),pfflag=document.getElementById('pfflag');
var expanded=false;
function cancelPendingUrlState(){
  if(pendingUrlState){pendingUrlState=false;setFilterLinksPending(false);}
}
function isoDate(d){
  return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);
}
// Objection-window checks run against "today" in Asia/Jerusalem (the permit
// deadline is local), recomputed at every page load (issue #153 pattern).
function todayJL(){
  try{return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Jerusalem'}).format(new Date());}
  catch(e){return isoDate(new Date());}
}
var TODAY=todayJL();
function validIso(v){
  if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(v))return false;
  var p=new Date(v+'T00:00:00');
  return !isNaN(p)&&isoDate(p)===v;
}
// Category per design: dated / pub-nodate (published, date unknown) /
// no-evidence. Rows from an older fragment lack data-pubcat - classify in JS.
var PUB_EVIDENCE={'\u05ea\u05d5\u05dd \u05ea\u05e7\u05d5\u05e4\u05ea \u05e4\u05e8\u05e1\u05d5\u05dd':1,'\u05e4\u05d5\u05e8\u05e1\u05de\u05d4 \u05d1\u05e7\u05e9\u05d4 \u05dc\u05d4\u05e7\u05dc\u05d4':1};
function pubcat(r,pub){
  var c=r.getAttribute('data-pubcat');
  if(c)return c;
  if(pub)return 'dated';
  if(PUB_EVIDENCE[r.getAttribute('data-status')]||r.getAttribute('data-pubend'))return 'pub-nodate';
  return 'no-evidence';
}
// Default order (#451): dated rows newest-first, then date-unknown rows in
// their own honest placement (pub-nodate before no-evidence), feed order
// kept stable inside each group.
function pubRank(r){
  var pub=r.getAttribute('data-pub')||'';
  var c=pubcat(r,pub);
  return c==='dated'?0:(c==='pub-nodate'?1:2);
}
function sortRows(){
  rows.forEach(function(r,i){r.__seq=i;});
  rows.sort(function(a,b){
    var ra=pubRank(a),rb=pubRank(b);
    if(ra!==rb)return ra-rb;
    if(ra===0){
      var pa=a.getAttribute('data-pub')||'',pb=b.getAttribute('data-pub')||'';
      if(pa!==pb)return pa<pb?1:-1; // ISO strings: newest first
    }
    var ta=a.getAttribute('data-tik')||'',tb=b.getAttribute('data-tik')||'';
    if(ta!==tb)return ta<tb?-1:1;
    return a.__seq-b.__seq;
  });
  var tb=document.querySelector('#permits-table tbody');
  if(tb)rows.forEach(function(r){tb.appendChild(r);});
}
// #521: group chips are the primary filter. Chips with data-default='1' start
// selected (the objection-relevant groups); the rest sit behind the
// "סטטוסים נוספים" disclosure and toggle the same way.
function selectedGroups(){
  var s={};
  pfgroups.querySelectorAll('.chip.sel').forEach(function(c){s[c.getAttribute('data-group')]=1;});
  return s;
}
{_NORM_SEARCH_JS}function match(r){
  var sel=selectedGroups();
  var g=r.getAttribute('data-group')||'unmapped';
  if(!sel[g])return false;
  // Scope flag (#521): out-of-area rows are hidden until "הצג גם מחוץ ל-7
  // השכונות" is checked; unknown-scope stays visible (fail visible).
  if(pfscope&&!pfscope.checked&&r.getAttribute('data-scope')==='out')return false;
  // "רק מועד התנגדות שלא עבר" applies to the open-objection group only:
  // a row whose (planned) window already closed is hidden while checked;
  // no end date = stays visible (deadline unknown, not elapsed).
  if(g==='obj'&&pfopenonly&&pfopenonly.checked){
    var pe=r.getAttribute('data-pubend');
    var evidence=r.getAttribute('data-publication-evidence')||'';
    // Keep raw planned end, but a later official publication makes that old
    // window stale. The new deadline remains unknown, not auto-extended.
    var superseded=validIso(evidence)&&validIso(pe)&&evidence>pe;
    if(pe&&pe<TODAY&&!superseded)return false;
  }
  if(!pfclosed.checked&&!pfstatus.value&&r.getAttribute('data-active')!=='1')return false;
  if(!searchMatches(r.__ns||(r.__ns=normSearch(r.getAttribute('data-search'))),pfq.value))return false;
  if(pfstatus.value&&r.getAttribute('data-status')!==pfstatus.value)return false;
  if(pfsug.value&&r.getAttribute('data-sug')!==pfsug.value)return false;
  var pub=r.getAttribute('data-pub');
  if(pub&&!validIso(pub))pub='';
  // Date filters apply to dated rows only (design option A): undated rows
  // are never hidden by the recency filter, they stay visible and marked.
  if(pub){
    var effFrom=pffrom.value;
    if(effFrom&&!validIso(effFrom))effFrom='';
    if(effFrom&&pub<effFrom)return false;
    if(pfto.value&&pub>pfto.value)return false;
  }
  return true;
}
function apply(){
  if(!fullLoaded&&defaultFailed){showLoadState();return;}
  if(!fullLoaded&&!isDefaultView()){loadFullPermits();showLoadState();return;}
  showLoadState();
  var n=0;
  rows.forEach(function(r){
    var vis=match(r);
    if(vis){n++;if(!expanded&&n>20)vis=false;}
    r.classList.toggle('filtered-out',!vis);
  });
  pmore.style.display=n>20?'':'none';
  pmore.textContent=expanded?'הצג 20 הראשונות':'הצג את כל '+n+' הבקשות';
  pfcount.textContent='מציג '+Math.min(n,expanded?n:20)+' מתוך '+n;
  // Split date-unknown counters (design): category 3 vs category 4, live.
  var c3=0,c4=0;
  rows.forEach(function(r){
    if(r.classList.contains('filtered-out'))return;
    var cat=pubcat(r,r.getAttribute('data-pub'));
    if(cat==='pub-nodate')c3++;else if(cat==='no-evidence')c4++;
  });
  pfunknown.textContent=(c3||c4)?'תאריך פרסום חסר: '+c3+' (פורסם, תאריך לא ידוע) · '+c4+' (אין ראיית פרסום)':'';
  pfflag.style.display=(pffrom.value&&!validIso(pffrom.value))?'':'none';
  document.dispatchEvent(new Event('permits-filtered'));
}
[pfq,pfstatus,pfsug,pffrom,pfto,pfclosed,pfopenonly,pfscope].forEach(function(el){
  if(!el)return;
  var h=function(){cancelPendingUrlState();expanded=false;apply();};
  el.addEventListener('input',h);el.addEventListener('change',h);
});
// Checking "הצג בקשות שהסתיימו" also selects the closed+issued group chips:
// the checkbox would otherwise reveal nothing while those groups are
// unselected (both gates must pass for a terminal row to show).
if(pfclosed&&pfgroups){
  pfclosed.addEventListener('change',function(){
    cancelPendingUrlState();
    pfgroups.querySelectorAll('.chip').forEach(function(c){
      var g=c.getAttribute('data-group');
      if(g==='closed'||g==='issued')c.classList.toggle('sel',pfclosed.checked);
    });
    expanded=false;apply();
  });
}
document.getElementById('pfreset').addEventListener('click',function(){
  cancelPendingUrlState();
  pfq.value='';pfstatus.value='';pfsug.value='';pffrom.value='';pfto.value='';
  pfclosed.checked=false;if(pfscope)pfscope.checked=false;if(pfopenonly)pfopenonly.checked=true;
  pfgroups.querySelectorAll('.chip').forEach(function(c){
    c.classList.toggle('sel',c.getAttribute('data-default')==='1');
  });
  expanded=false;apply();
});
pmore.addEventListener('click',function(){cancelPendingUrlState();expanded=!expanded;apply();});
function statusClass(st){
  st=st||'';
  if(st.indexOf('נסגרה')!==-1)return 'c-closed';
  if(st.indexOf('הופק')!==-1)return 'c-approved';
  if(st.indexOf('פרסום')!==-1||st.indexOf('הודעות לפני תקנה')!==-1)return 'c-deposit';
  if(st.indexOf('וועד')!==-1||st.indexOf('ועדת')!==-1||st.indexOf('רשות הרישוי')!==-1)return 'c-review';
  if(st.indexOf('טיוטת היתר')!==-1)return 'c-cond';
  return 'c-inproc';
}
var GROUP_LABELS={'unmapped':'לא מסווג'};
var GROUP_CLASS={'unmapped':'c-inproc'};
function ensureGroupChips(){
  // #622: subset rows can introduce a status absent from the weekly shell.
  // Add the selected fail-visible chip without inventing full-dataset counts.
  var have={};
  pfgroups.querySelectorAll('.chip').forEach(function(c){have[c.getAttribute('data-group')]=1;});
  rows.forEach(function(r){
    var k=r.getAttribute('data-group')||'unmapped';
    if(have[k])return;
    have[k]=1;
    var c=document.createElement('span');
    c.className='chip '+(GROUP_CLASS[k]||'c-inproc')+' sel';
    c.setAttribute('data-group',k);
    c.setAttribute('data-default','1');
    c.setAttribute('data-label',GROUP_LABELS[k]||k);
    c.textContent=GROUP_LABELS[k]||k;
    pfgroups.insertBefore(c,pfgroups.querySelector('.more-statuses'));
  });
}
function rebuildDerived(){
  ensureGroupChips(); // One chip builder for subset and full-list paths (#625).
  // #414: chips, filter options and counters derive from the loaded fragment
  // rows (the live source), not the weekly index.html shell; #521: the legend
  // counts are per status GROUP, raw statuses fill the select.
  var counts={},sugs={},closed=0,gcounts={},outscope=0,i,st,sug,g;
  var dated=0,planned=0;
  for(i=0;i<rows.length;i++){
    if(validIso(rows[i].getAttribute('data-pub')||''))dated++;
    if(validIso(rows[i].getAttribute('data-pubend')||''))planned++;
    st=rows[i].getAttribute('data-status')||'';
    if(st)counts[st]=(counts[st]||0)+1;
    sug=rows[i].getAttribute('data-sug')||'';
    if(sug)sugs[sug]=1;
    if(rows[i].getAttribute('data-active')==='0')closed++;
    g=rows[i].getAttribute('data-group')||'unmapped';
    gcounts[g]=(gcounts[g]||0)+1;
    if(rows[i].getAttribute('data-scope')==='out')outscope++;
  }
  var coverage=document.getElementById('permit-coverage-counts');
  if(coverage)coverage.textContent=rows.length+' בקשות במאגר; '+dated+
    ' עם תאריך תחילת פרסום; '+planned+' עם סיום פרסום מתוכנן; '+
    (rows.length-dated)+' ללא תאריך תחילת פרסום.';
  pfgroups.querySelectorAll('.chip').forEach(function(c){
    var k=c.getAttribute('data-group');
    c.textContent=c.getAttribute('data-label')+' ('+(gcounts[k]||0)+')';
    delete gcounts[k];
  });
  function refill(sel,first,values){
    var keep=sel.value;
    sel.innerHTML='';
    var o=document.createElement('option');o.value='';o.textContent=first;sel.appendChild(o);
    values.forEach(function(v){var x=document.createElement('option');x.value=v;x.textContent=v;sel.appendChild(x);});
    sel.value=values.indexOf(keep)!==-1?keep:'';
  }
  refill(pfstatus,'כל סטטוסי המקור',Object.keys(counts).sort());
  refill(pfsug,'כל הסוגים',Object.keys(sugs).sort());
  if(pfclosed&&pfclosed.parentNode&&pfclosed.parentNode.lastChild){
    pfclosed.parentNode.lastChild.textContent=' הצג בקשות שהסתיימו ('+closed+')';
  }
  if(pfscope&&pfscope.parentNode&&pfscope.parentNode.lastChild){
    pfscope.parentNode.lastChild.textContent=' הצג גם מחוץ ל-7 השכונות ('+outscope+')';
  }
}
if(pfgroups){
  pfgroups.addEventListener('click',function(ev){
    var c=ev.target.closest?ev.target.closest('.chip'):null;
    if(!c||!pfgroups.contains(c))return;
    cancelPendingUrlState();c.classList.toggle('sel');
    expanded=false;apply();
  });
}
// #573: a newer publication list can precede the permit-feed status update.
// Overlay display evidence only. Never rewrite the raw source status or create
// a deadline. Only confirmed in-scope, valid-dated, nonterminal rows qualify.
// 90 days is a display-evidence freshness policy, NOT a legal deadline.
var PUBLICATION_EVIDENCE_MAX_DAYS=90;
var publicationEvidence=[];
function applyPublicationEvidence(){
  var byId={};
  publicationEvidence.forEach(function(p){
    if(currentEvidence(p))byId[p.tik_num]=p;
  });
  rows.forEach(function(r){
    var p=byId[r.getAttribute('data-tik')];
    if(!p||r.getAttribute('data-active')!=='1')return;
    var current=r.getAttribute('data-pub')||'';
    // Feed status_date may be absent (all committed rows at this change);
    // then only the recency/current-publication and conservative postpub guards apply.
    var stage=r.getAttribute('data-statusdate')||'';
    var group=r.getAttribute('data-group');
    // #804: unknown official deadline is not a safe blank or a computed date.
    // Keep source planned dates and viewer links untouched. Equal-date evidence
    // still needs the warning even when it cannot promote the display again.
    if((!validIso(current)||p.publication_date>=current)&&
       (group==='obj'||(!validIso(stage)||p.publication_date>=stage))&&
       (group!=='postpub'||(validIso(stage)&&p.publication_date>stage))){
      var note=r.querySelector('[data-deadline-note]');
      if(note){
        note.textContent=validIso(p.objection_deadline)?'':
          ' מועד התנגדות לא ידוע - יש לבדוק בפרסום העירוני';
        note.className=validIso(p.objection_deadline)?'':'pub-missing';
      }
    }
    if(group==='postpub'&&(!validIso(stage)||p.publication_date<=stage))return;
    if(validIso(stage)&&p.publication_date<=stage)return;
    // An older/repeated listing cannot resurrect a later workflow state.
    if(validIso(current)&&p.publication_date<=current)return;
    // A publication sighting does not establish filing eligibility for paid advance.
    r.setAttribute('data-group',r.getAttribute('data-status')==='שולמה מקדמה'?'pubcheck':'obj');
    r.setAttribute('data-publication-evidence',p.publication_date);
    r.setAttribute('data-pub',p.publication_date);
    r.setAttribute('data-pubcat','dated');
    var cell=r.querySelector('[data-publication-cell]');
    if(cell){
      cell.textContent=p.publication_date.split('-').reverse().join('.')+' (פרסום עירוני; קבוצת התצוגה נקבעת לפי הפרסום)';
      cell.setAttribute('data-iso',p.publication_date);
    }
  });
}
function currentEvidence(p){
  // The overlay window, shared with the #441 subset safety net.
  if(!p||p.in_polygon!==true||!validIso(p.publication_date))return false;
  var age=(Date.parse(TODAY+'T00:00:00Z')-Date.parse(p.publication_date+'T00:00:00Z'))/86400000;
  return age>=0&&age<=PUBLICATION_EVIDENCE_MAX_DAYS;
}
fetch('publications_active.json').then(function(r){if(!r.ok)throw new Error('unavailable');return r.json();}).then(function(list){
  if(!Array.isArray(list))throw new Error('invalid publication list');
  publicationEvidence=list;
  try{
    applyPublicationEvidence();sortRows();if(fullLoaded)rebuildDerived();
    // #757: complete a deferred URL-state restore a failed post-install never
    // reached: clearing the render retry below without it would strand the
    // pending state with no way to re-run. Must precede apply() so the
    // restored controls filter this render. Only once the full rows are in:
    // group chips introduced by the full rows (ensureGroupChips, #622) do not
    // exist on the subset, so an earlier restore would fail validation and
    // silently drop the link's group selection.
    if(fullLoaded&&pendingUrlState&&permitLink){permitLink.restore();pendingUrlState=false;setFilterLinksPending(false);}
    apply();
    if(window.__renderUrgent)window.__renderUrgent();
    // A successful re-render supersedes any earlier render failure.
    if(renderFailed){renderFailed=false;window.__permitsRenderFailed=false;pfload.textContent='';}
  }catch(err){
    showRenderRetry(function(){
      applyPublicationEvidence();sortRows();if(fullLoaded)rebuildDerived();
      if(fullLoaded&&pendingUrlState&&permitLink){permitLink.restore();pendingUrlState=false;setFilterLinksPending(false);}
      apply();
      if(window.__renderUrgent)window.__renderUrgent();
    });
  }
  // Data-state signaling is not rendering: it must fire even when the render
  // above failed, or the #441 safety net never learns about new evidence.
  window.__permitPublicationEvidenceLoaded=true;
  document.dispatchEvent(new Event('publication-evidence-loaded'));
}).catch(function(){window.__permitPublicationEvidenceFailed=true;});
// #441: the page first loads the small default-view subset
// (permits-default.html: active default-group rows not out of scope, plus
// rows with in-polygon publication evidence). The full permits.html loads
// once, through one shared promise, on the first interaction that leaves the
// default view. A non-default view never shows subset results: it shows a
// loading state, and on failure a retry button while the subset stays.
var fullLoaded=false,fullPromise=null,fullFailed=false;
// Closure state; the window.__permits* flags are test hooks only.
var defaultFailed=false,evidenceNeedsFull=false;
var defaultLoaded=false,evidenceLoaded=false,pendingUrlState=false,permitLink=null;
function setFilterLinksPending(v){
  ['copy-plan-link','copy-permit-link'].forEach(function(id){var b=document.getElementById(id);if(b)b.disabled=v;});
}
var pfload=document.createElement('span');
pfload.id='pfload';pfload.setAttribute('role','status');
if(pfcount&&pfcount.parentNode)pfcount.parentNode.insertBefore(pfload,pfcount.nextSibling);
function installRows(h){
  var tb=document.querySelector('#permits-table tbody');if(!tb)return false;
  tb.innerHTML=h;
  rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  ensureGroupChips();
  applyPublicationEvidence();
  sortRows();
  return true;
}
function isDefaultView(){
  if(pendingUrlState)return false;
  if(expanded||pfq.value.trim()||pfstatus.value||pfsug.value||pffrom.value||pfto.value)return false;
  if(pfclosed.checked||(pfscope&&pfscope.checked)||(pfopenonly&&!pfopenonly.checked))return false;
  var same=true;
  pfgroups.querySelectorAll('.chip').forEach(function(c){
    if(c.classList.contains('sel')!==(c.getAttribute('data-default')==='1'))same=false;
  });
  return same;
}
function showRetry(){
  pfload.textContent='טעינת הרשימה המלאה נכשלה. ';
  var b=document.createElement('button');
  b.type='button';b.id='pfretry';b.textContent='נסו שוב';
  b.addEventListener('click',function(){loadFullPermits();});
  pfload.appendChild(b);
}
function showLoadState(){
  if(fullLoaded){if(!renderFailed)pfload.textContent='';return;}
  if(isDefaultView()&&!defaultFailed){
    // The subset view stays visible. A full load the evidence safety net
    // asked for (a current publication outside the subset) must still say
    // when it failed, or that permit is silently missing.
    // A failed full fetch for evidence missing from the subset is the
    // blocking problem: show its retry first. The render failure re-surfaces
    // through the post-install catch once the fetch succeeds.
    if(fullFailed&&evidenceNeedsFull)showRetry();
    // A render failure otherwise stays visible until its retry succeeds: a
    // later publications/apply cycle must not wipe it in the default view.
    else if(renderFailed){/* keep the render retry visible */}
    else pfload.textContent='';
    return;
  }
  rows.forEach(function(r){r.classList.add('filtered-out');});
  pmore.style.display='none';
  pfcount.textContent='';pfunknown.textContent='';
  if(fullFailed)showRetry();
  else pfload.textContent='טוען את הרשימה המלאה…';
}
// #624: a post-install render failure is not a load failure. The rows are
// already in the table, so the honest state is "loaded, processing failed"
// with a retry that re-runs only the post-install steps - not a refetch.
var renderFailed=false;
function showRenderRetry(rerun){
  renderFailed=true;window.__permitsRenderFailed=true;
  pfload.textContent='הרשימה נטענה אך עיבוד התצוגה נכשל. ';
  var b=document.createElement('button');
  b.type='button';b.id='pfrenderretry';b.textContent='נסו שוב';
  b.addEventListener('click',function(){
    try{rerun();renderFailed=false;window.__permitsRenderFailed=false;pfload.textContent='';}
    catch(err){showRenderRetry(rerun);}
  });
  pfload.appendChild(b);
}
function runFullPostInstall(){
  rebuildDerived();
  if(pendingUrlState&&permitLink){permitLink.restore();pendingUrlState=false;setFilterLinksPending(false);}
  apply();
  if(window.__renderUrgent)window.__renderUrgent();
}
function loadFullPermits(){
  if(fullLoaded)return Promise.resolve(true);
  if(fullPromise)return fullPromise;
  fullFailed=false;window.__permitsFailed=false;
  fullPromise=fetch('permits.html').then(function(r){if(!r.ok)throw new Error('http');return r.text();}).then(function(h){
    if(!installRows(h))throw new Error('permit table unavailable');
    fullLoaded=true;
    try{runFullPostInstall();renderFailed=false;window.__permitsRenderFailed=false;pfload.textContent='';}
    catch(err){
      // The rows stay installed for the retry, but never unfiltered under an
      // active non-default view: replay the filter before surfacing the state.
      try{apply();}catch(ignore){}
      showRenderRetry(runFullPostInstall);
    }
    window.__permitsLoaded=true;
    return true;
  }).catch(function(){
    fullPromise=null;fullFailed=true;window.__permitsFailed=true;
    showLoadState();
    return false;
  });
  showLoadState();
  return fullPromise;
}
window.__loadFullPermits=loadFullPermits;
// Safety net for the #573 overlay: the publication list refreshes daily,
// independently of the permit render. Evidence the overlay would apply today
// for a tik missing from the subset means the subset may be older than the
// evidence: load it all. Old evidence (outside the overlay window, e.g. for
// closed requests) promotes nothing, so it must not cost the full fetch.
function evidenceOutsideSubset(){
  var have={};
  rows.forEach(function(r){have[r.getAttribute('data-tik')]=1;});
  return publicationEvidence.some(function(p){return currentEvidence(p)&&!have[p.tik_num];});
}
function checkSubsetAgainstEvidence(){
  if(!fullLoaded&&defaultLoaded&&evidenceLoaded&&evidenceOutsideSubset()){evidenceNeedsFull=true;loadFullPermits();}
}
document.addEventListener('publication-evidence-loaded',function(){evidenceLoaded=true;checkSubsetAgainstEvidence();});
fetch('permits-default.html').then(function(r){if(!r.ok)throw new Error('http');return r.text();}).then(function(h){
  if(fullLoaded)return;
  if(!installRows(h))return;
  // #624: a subset render failure keeps the subset rows and says so; it is
  // not a subset fetch failure and must not trigger a misleading full reload.
  try{
    apply();
    if(window.__renderUrgent)window.__renderUrgent();
  }catch(err){
    try{apply();}catch(ignore){}
    showRenderRetry(function(){apply();if(window.__renderUrgent)window.__renderUrgent();});
  }
  defaultLoaded=true;window.__permitsDefaultLoaded=true;
  checkSubsetAgainstEvidence();
}).catch(function(){
  // No subset (an older deploy, or a fetch error): fall back to the full list.
  defaultFailed=true;window.__permitsDefaultFailed=true;loadFullPermits();
});
permitLink=window.GinotFilterLinks.register('permit',
  {pfq:1,pfstatus:1,pfsug:1,pffrom:1,pfto:1,pfclosed:1,pfopenonly:1,pfscope:1}, {
  keys:['expanded','groups'],
  restore:function(p,n){
    if(p.get(n+'.expanded')==='1')expanded=true;
    var raw=p.get(n+'.groups'),chips=Array.from(pfgroups.querySelectorAll('.chip'));
    var wanted=raw&&raw.length<=500?raw.split(','):[];
    var valid=raw!==null&&raw.length<=500&&wanted.every(function(k){
      return chips.some(function(c){return c.getAttribute('data-group')===k;});
    });
    if(valid){
      chips.forEach(function(c){c.classList.toggle('sel',wanted.indexOf(c.getAttribute('data-group'))!==-1);});
    }else if(pfclosed.checked){
      chips.forEach(function(c){var g=c.getAttribute('data-group');if(g==='closed'||g==='issued')c.classList.add('sel');});
    }
  },
  write:function(p,n){
    if(expanded)p.set(n+'.expanded','1');
    var chips=Array.from(pfgroups.querySelectorAll('.chip'));
    if(pfclosed.checked||chips.some(function(c){return c.classList.contains('sel')!==(c.getAttribute('data-default')==='1');})){
      p.set(n+'.groups',chips.filter(function(c){return c.classList.contains('sel');}).map(function(c){return c.getAttribute('data-group');}).sort().join(','));
    }
  }
});
pendingUrlState=permitLink.hasState;
if(pendingUrlState){setFilterLinksPending(true);loadFullPermits();}
sortRows();apply();
})();
""".replace("{_NORM_SEARCH_JS}", _NORM_SEARCH_JS)


# Section: Main page rendering


def _social_meta(council_name: str, base_url: str, preview_image: bool) -> str:
    """Open Graph + Twitter card tags. The image URL must be absolute, so the
    image tags appear only with a base_url and a generated og.png."""
    title = f"תכניות תכנון ובנייה - {council_name}"
    desc = "תכניות והיתרים באזור: סטטוס, מועדי הפקדה ותאריך אחרון להתנגדות (משוער)."
    tags = [
        ("name", "description", desc),
        ("property", "og:type", "website"),
        ("property", "og:locale", "he_IL"),
        ("property", "og:title", title),
        ("property", "og:description", desc),
    ]
    if base_url:
        tags.append(("property", "og:url", base_url))
    if base_url and preview_image:
        tags += [
            ("property", "og:image", base_url.rstrip("/") + "/og.png"),
            ("property", "og:image:width", "1200"),
            ("property", "og:image:height", "630"),
            ("property", "og:image:alt", title),
            ("name", "twitter:card", "summary_large_image"),
            ("name", "twitter:image", base_url.rstrip("/") + "/og.png"),
        ]
    else:
        tags.append(("name", "twitter:card", "summary"))
    tags += [("name", "twitter:title", title), ("name", "twitter:description", desc)]
    return "\n".join(f'<meta {k}="{n}" content="{_e(v)}">' for k, n, v in tags)


def render_index(
    rows: list[dict],
    changes: list[dict],
    generated: str,
    council_name: str,
    permits: list[dict] | None = None,
    base_url: str = "",
    preview_image: bool = False,
    reviews: dict[str, str] | None = None,
    rows_file: str | None = None,
    permits_file: str | None = None,
    permits_default_file: str | None = None,
    evidence_tiks: frozenset = frozenset(),
) -> str:
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
        source = _community_source_link(r["pl_number"])
        if not url:
            return source or "—"
        return (
            f"<a class='ai-review' href='{_e(url)}' "
            f"title='סיכום נקודות לדיון שהופק באמצעות AI - אינו מסמך רשמי'>סקירה</a>"
        ) + source

    def tr(r):
        search = _e((r["pl_number"] + " " + (r.get("pl_name") or "")).lower())
        attrs = (
            f"data-status='{_e(r.get('station_desc'))}' data-flag='{_e(r.get('inside_flag'))}' "
            f"data-recv='{_e(_iso(r.get('receiving_date')))}' data-dep='{_e(_iso(_deposit_date(r)))}' "
            f"data-open='{1 if r['_open_obj'] else 0}' data-obj='{_e(_iso(r.get('objection_deadline_derived_2m_from_publication')))}' data-num='{_e(r['pl_number'])}' data-name='{_e((r.get('pl_name') or '').lower())}' data-area='{_e(r['pl_area_dunam'])}' "
            f"data-active='{1 if r['_open_obj'] or _is_active(r) else 0}' data-search='{search}'"
        )
        cls = "new" if r.get("_is_new") else ""
        return (
            f"<tr class='{cls}' {attrs}>"
            f"<td><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a></td>"
            f"<td>{_e(r['pl_name'])}</td><td>{chip(r['station_desc'])}</td>"
            f"<td>{_date_cell(r['receiving_date'])}</td>"
            f"<td>{_date_cell(_deposit_date(r))}</td>"
            f"<td class='derived'>{_date_cell(r.get('objection_deadline_derived_2m_from_publication'))}</td>"
            f"<td>{_e(r['pl_area_dunam'])}</td><td>{review_cell(r)}</td></tr>"
        )

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
        iso = _iso(r.get("objection_deadline_derived_2m_from_publication"))
        if not iso:
            return False
        try:
            dd = (datetime.date.fromisoformat(iso) - gen_d).days
        except ValueError:
            return False
        return 0 <= dd <= URGENT_DAYS

    urgent = sorted(
        (r for r in rows if _urgent_window(r)),
        key=lambda r: _iso(r.get("objection_deadline_derived_2m_from_publication")),
    )
    urgent_html = (
        "".join(
            f"<li><a href='{_e(r['mavat_url'])}'>{_e(r['pl_number'])}</a> {_e(r['pl_name'])} - "
            f"אחרון להתנגדות (משוער): {_e(_fmt(r.get('objection_deadline_derived_2m_from_publication')))}</li>"
            for r in urgent
        )
        or "<li>אין</li>"
    )
    changes_html = (
        "".join(
            f"<li>{_e(c['kind'])}: <a href='{_e(c['mavat_url'])}'>{_e(c['pl_number'])}</a> {_e(c['pl_name'])}"
            + (
                f" ({_e(c.get('from'))} → {_e(c.get('to'))})"
                if c["kind"] == "status_change"
                else ""
            )
            + "</li>"
            for c in changes
        )
        or "<li>אין שינויים מהסריקה הקודמת</li>"
    )
    status_opts = "".join(f"<option value='{_e(s)}'>{_e(s)}</option>" for s in statuses)
    n_approved = sum(1 for r in rows if not r["_open_obj"] and not _is_active(r))
    legend = (
        '<div class="legend plan-legend"><b>מקרא סטטוסים:</b> '
        + " ".join(chip(s) for s in statuses)
        + "</div>"
    )
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
<link rel="stylesheet" href="style.css"><link rel="stylesheet" href="plan-map.css">{_ANALYTICS_SNIPPET}</head><body>
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
<input id="fq" type="search" placeholder="חיפוש מספר / שם; או עם |" title="לחיפוש חלופות הפרידו עם |, למשל: פלמח 41 | פלמח 49. פסיק נשאר תו רגיל. החיפוש מתעלם מגרש ומרכאות (׳ ״ ' &quot; ’), ממקפים, מניקוד ומרווחים כפולים">
<select id="fstatus"><option value="">כל הסטטוסים</option>{status_opts}</select>
<select id="fflag"><option value="">בתוך + חלקי</option><option value="inside">בתוך השטח</option><option value="partial">חפיפה חלקית</option></select>
<label><input type="checkbox" id="fobj"> חלון התנגדות פתוח (משוער)</label>
<label><input type="checkbox" id="fappr"> הצג תכניות מאושרות ({n_approved})</label>
<label>מתאריך <input type="date" id="ffrom"></label>
<label>עד <input type="date" id="fto"></label>
<button id="freset" type="button">נקה סינון</button>
<button id="copy-plan-link" type="button">העתק קישור לסינון</button>
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
{_permits_section(permits or [], rows_file=permits_file, default_rows_file=permits_default_file, evidence_tiks=evidence_tiks)}
{mapview.PANEL}
<h2>דחוף להתנגדות</h2><ul id="urgent-list">{urgent_html}</ul>
<h2>שינויים אחרונים</h2><ul id="changes-list">{changes_html}</ul>
{stats_html}
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת גינות העיר. קוד מקור ונתונים:
<a href="https://github.com/reihlinstinct/ginot-hair-plans">GitHub</a>
&middot; <a href="about.html">אודות ומקורות נתונים</a>
&middot; <a href="email.html">קבלת מייל על תוכנית</a>
&middot; <a href="https://github.com/reihlinstinct/ginot-hair-plans/blob/main/CONTRIBUTING.md">איך לתרום</a>
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
<script src="filter-links.js"></script>
<script>{_JS}{_PERMITS_JS}{_STATS_JS}</script>
<script>// Strip free-text search params from the URL before the analytics beacon
// executes (deferred), so search text never leaves the browser in the ping (#821).
(function(){{try{{var u=new URL(location.href),dirty=false;
['plan.fq','permit.pfq'].forEach(function(k){{if(u.searchParams.has(k)){{u.searchParams.delete(k);dirty=true;}}}});
if(dirty)history.replaceState(null,'',u);}}catch(e){{}}}})();</script>
</body></html>"""


# Section: Privacy-limited usage counters

_STATS_JS = r"""
// Anonymous usage statistics (#821): aggregate counters only. A search is
// reported ONLY when it exactly matches a value from the site's own data
// (a plan number/name, street, permit number, or filter value) after the
// same folding the search box uses; anything else is reported as "other".
// Raw free text never leaves the browser, and the server re-validates every
// key against its own dictionary before storing it. One event per distinct
// key per page load.
(function(){
{_NORM_SEARCH_JS}
var API='https://ginot-hair-api.reihlinstinct.workers.dev';
var sent={};
function sendStat(e,k){
  var id=e+'|'+k;
  if(sent[id])return;
  sent[id]=1;
  try{
    var blob=new Blob([JSON.stringify({e:e,k:k})],{type:'text/plain'});
    if(navigator.sendBeacon&&navigator.sendBeacon(API+'/stats/event',blob))return;
    fetch(API+'/stats/event',{method:'POST',body:blob,keepalive:true}).catch(function(){});
  }catch(err){}
}
// Same rule as the server's streetOf (worker/api.mjs): leading tokens until
// the first token containing a digit.
function streetOf(addr){
  var t=String(addr||'').trim().split(/\s+/),out=[];
  for(var i=0;i<t.length;i++){if(/\d/.test(t[i]))break;out.push(t[i]);}
  return out.join(' ');
}
var planDict=null,permitDict=null;
function buildPlanDict(){
  if(planDict)return planDict;
  planDict={};
  document.querySelectorAll('#plans tbody tr').forEach(function(r){
    var num=r.getAttribute('data-num')||'';
    if(num)planDict[normSearch(num)]=num;
    var nm=r.getAttribute('data-name')||'';
    // data-name is lowercased; report the exact plan number for a name hit.
    if(nm&&num)planDict[normSearch(nm)]=num;
    var st=r.getAttribute('data-status')||'';
    if(st)planDict[normSearch(st)]=st;
  });
  return planDict;
}
function buildPermitDict(){
  if(permitDict)return permitDict;
  permitDict={};
  document.querySelectorAll('#permits-table tbody tr').forEach(function(r){
    var tik=r.getAttribute('data-tik')||'';
    if(tik)permitDict[normSearch(tik)]=tik;
    var st=r.getAttribute('data-status')||'';
    if(st)permitDict[normSearch(st)]=st;
    var sug=r.getAttribute('data-sug')||'';
    if(sug)permitDict[normSearch(sug)]=sug;
    var td=r.querySelector('td:nth-child(2)');
    var addr=td&&td.firstChild?td.firstChild.textContent:'';
    var street=streetOf(addr);
    if(street)permitDict[normSearch(street)]=street;
  });
  return permitDict;
}
var tPlans,tPermits;
document.addEventListener('plans-filtered',function(){
  clearTimeout(tPlans);tPlans=setTimeout(reportPlans,1200);
});
document.addEventListener('permits-filtered',function(){
  clearTimeout(tPermits);tPermits=setTimeout(reportPermits,1200);
});
function reportPlans(){
  var fq=document.getElementById('fq');if(!fq)return;
  var q=normSearch(fq.value.trim());
  if(q)sendStat('search',buildPlanDict()[q]||'other');
  var fs=document.getElementById('fstatus');
  if(fs&&fs.value)sendStat('filter',fs.value);
}
function reportPermits(){
  var pfq=document.getElementById('pfq');if(!pfq)return;
  var q=normSearch(pfq.value.trim());
  if(q)sendStat('permits_search',buildPermitDict()[q]||'other');
  var st=document.getElementById('pfstatus');
  if(st&&st.value)sendStat('permits_filter',st.value);
  var sug=document.getElementById('pfsug');
  if(sug&&sug.value)sendStat('permits_filter',sug.value);
}
})();
""".replace("{_NORM_SEARCH_JS}", _NORM_SEARCH_JS)


# Section: Site output orchestration


def render_site(
    rows: list[dict],
    changes: list[dict],
    out_dir: str,
    council_name: str = "גינות העיר",
    base_url: str = "",
    permits_path: str | None = None,
    council_geojson: str | None = None,
    plans_dir: str = "plans",
    external_reviews_path: str = "data/external_reviews.json",
):
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
    for path in sorted(
        glob.glob(os.path.join(plans_dir, "*", "analysis", "talking_points_*.md"))
    ):
        m = _re.fullmatch(r"talking_points_(\d+-\d+)\.md", os.path.basename(path))
        if m:
            reviews[m.group(1)] = f"reviews/talking_points_{m.group(1)}.html"
            with open(path, encoding="utf-8") as rf:
                review_pages[m.group(1)] = rf.read()
    generated = today_il().isoformat()
    permits = []
    if permits_path:
        try:
            with open(permits_path, encoding="utf-8") as pf:
                permits = json.load(pf).get("requests", [])
        except (FileNotFoundError, json.JSONDecodeError):
            permits = []
    from .mapdata import write_permit_points

    permit_map = write_permit_points(
        permits,
        os.path.join(
            os.path.dirname(permits_path or "data/permit_requests.json"),
            "ginot_hair_parcels.geojson",
        ),
        f"{out_dir}/permit-points.json",
    )
    missing_positions = set(permit_map["missing_location"])
    permits = [
        dict(p, _map_missing=p.get("tik_num") in missing_positions) for p in permits
    ]
    # Public normalized publication metadata only, never permit-file documents.
    publications_path = os.path.join(
        os.path.dirname(permits_path or "data/permit_requests.json"),
        "publications_active.json",
    )
    from .publications import write_projection

    write_projection(publications_path, f"{out_dir}/publications_active.json")
    from . import preview

    sort_rows(rows)  # annotates _open_obj, which the preview card counts
    has_img = preview.render_preview(
        rows,
        council_name,
        generated,
        "data/council_ginot_hair.geojson"
        if os.path.exists("data/council_ginot_hair.geojson")
        else "data/council.geojson",
        f"{out_dir}/og.png",
    )
    with open(f"{out_dir}/style.css", "w", encoding="utf-8") as fh:
        fh.write(_CSS)
    with open(f"{out_dir}/index.html", "w", encoding="utf-8") as fh:
        fh.write(
            render_index(
                rows,
                changes,
                generated,
                council_name,
                permits,
                base_url=base_url,
                preview_image=has_img,
                reviews=reviews,
                rows_file=f"{out_dir}/rows.html",
                permits_file=f"{out_dir}/permits.html",
                permits_default_file=f"{out_dir}/permits-default.html",
                evidence_tiks=publication_evidence_tiks(publications_path),
            )
        )
    if permits_path:
        # Rewrite every run, even with zero requests (#530): an empty list is
        # the correct state, and skipping the write would leave the previous
        # ids published, so the submit worker would keep accepting reviews for
        # requests no longer in the table.
        write_permit_ids(permits, f"{out_dir}/permit-ids.json")
    from . import external_reviews as _er

    external = _er.load(external_reviews_path)
    if _er.validate_entries(external):
        external = []  # never render an invalid file
    if review_pages:
        os.makedirs(f"{out_dir}/reviews", exist_ok=True)
        row_by_number = {r.get("pl_number"): r for r in rows}
        for pl, md_text in review_pages.items():
            row = row_by_number.get(pl, {"pl_number": pl})
            review_image = preview.render_review_preview(
                row, generated, f"{out_dir}/reviews/og_{pl}.png"
            )
            with open(
                f"{out_dir}/reviews/talking_points_{pl}.html", "w", encoding="utf-8"
            ) as fh:
                fh.write(
                    render_review(
                        pl,
                        md_text,
                        generated,
                        council_name,
                        base_url,
                        row.get("pl_name") or "",
                        review_image,
                        _er.render_section(external, pl),
                    )
                )
    with open(f"{out_dir}/about.html", "w", encoding="utf-8") as fh:
        fh.write(render_about(generated, council_name))
    from .page_email import render_email_page

    with open(f"{out_dir}/email.html", "w", encoding="utf-8") as fh:
        fh.write(render_email_page(rows, generated, council_name))
    with open(f"{out_dir}/sources.html", "w", encoding="utf-8") as fh:
        fh.write(_SOURCES_REDIRECT)
    with open(f"{out_dir}/feed.xml", "w", encoding="utf-8") as fh:
        fh.write(render_feed(changes, generated, council_name, base_url))
    with open(f"{out_dir}/data.json", "w", encoding="utf-8") as fh:
        json.dump(
            {
                "generated": generated,
                "rows": public_project(rows, "rows"),
                "changes": public_project(changes, "changes"),
                "permits": public_project(permits, "permits"),
            },
            fh,
            ensure_ascii=False,
        )
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
        json.dump(
            {
                "generated": generated,
                "definition": "station_desc != 'אישור' - תכניות שעדיין בתהליך תכנוני",
                "count": len(open_rows),
                "plans": public_project(open_rows, "plans"),
            },
            fh,
            ensure_ascii=False,
        )
