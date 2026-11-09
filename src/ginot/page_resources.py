"""Shared literal page resources and HTML escaping. No rendering side effects."""

import html

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
.cta-email{display:inline-block;background:#2f7f68;color:#fff;font-weight:700;text-decoration:none;border-radius:8px;padding:10px 16px;min-height:24px}
.cta-email:hover,.cta-email:focus{background:#101f5b;color:#fff}
.legend{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px;margin:4px 0 8px}
.legend .chip{cursor:pointer}
.more-statuses{flex:1 1 100%}
.more-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.more-statuses summary{display:inline-block;cursor:pointer;color:#101f5b;font-weight:700}
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
.pub-missing{color:#8a6d00;font-size:.85em;font-style:italic}
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
#permits-table td:nth-child(9)::before{content:"סקירת AI"}
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


_SOURCES_ROWS = [
    (
        "תכניות במינהל",
        "שירות התכנון הציבורי (iplan), מנהל התכנון",
        "מספר ושם התכנית, סטטוס, תאריכי קליטה והפקדה, שטח; מועד אחרון להתנגדות מחושב (הערכה)",
        "רענון שבועי (יום שלישי) ורענונים ידניים",
        '<a href="data.json">data.json</a>',
    ),
    (
        "פרסומי הפקדה",
        "land.gov.il - מינהל מקרקעי ישראל",
        "תאריכי פרסום ההפקדה בעיתונים וביתרונות לכל תכנית",
        "רענון שבועי",
        '<a href="https://land.gov.il">land.gov.il</a>',
    ),
    (
        "בקשות היתר",
        "איתור נתונים ברישוי, עיריית ירושלים",
        "מספר בקשה, כתובת, מהות, סוג, סטטוס, תאריכי סטטוס ופרסום, גוש וחלקה",
        "סריקת חלקות באצוות ליליות (בשלבי השלמה ראשונית) והעשרת סטטוסים",
        '<a href="https://ykpubdata.jerusalem.muni.il/">איתור נתונים ברישוי</a>',
    ),
    (
        "מסמכי תכנית וסקירות AI",
        'מאב"ת - מערכת איתור בינוי ותכניות',
        "מסמכי הוראות, תשריט והודעות; סיכומי נקודות לדיון שהופקו באמצעות AI (מסומנים, אינם מסמך רשמי)",
        "לפי צורך, לתכניות נבחרות",
        '<a href="https://mavat.iplan.gov.il/">מאב"ת</a>',
    ),
    (
        "גבול המינהל",
        "קובץ גבול גיאוגרפי במאגר",
        "פוליגון שטח המינהל הקהילתי (geojson)",
        "עדכון ידני בשינוי גבול",
        '<a href="https://github.com/reihlinstinct/ginot-hair-plans/tree/main/data">תיקיית data</a>',
    ),
]


_ANALYTICS_SNIPPET = (
    "\n<!-- Cloudflare Web Analytics: anonymous, cookieless visit counter (issue #821) -->"
    "\n<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js'"
    ' data-cf-beacon=\'{"token": "ddb51e25c65545bea5cda52329983b4c"}\'></script>'
)


_SOURCES_REDIRECT = """<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=about.html">
<title>מקורות נתונים</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022">
<!-- Cloudflare Web Analytics: anonymous, cookieless visit counter (issue #821) -->
<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{"token": "ddb51e25c65545bea5cda52329983b4c"}'></script></head>
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


def _e(s):
    return html.escape(str(s or ""))


def _iso(d) -> str:
    d = (d or "").strip()[:10]
    if len(d) < 10 or d[4] != "-" or d[7] != "-":
        return ""
    try:
        m, day = int(d[5:7]), int(d[8:10])
    except ValueError:
        return ""
    # scraper-sourced field: reject impossible months/days so a malformed
    # publication_start degrades to "date unknown" instead of a bogus date
    return d if 1 <= m <= 12 and 1 <= day <= 31 else ""


def _fmt(d) -> str:
    iso = _iso(d)
    return f"{iso[8:10]}.{iso[5:7]}.{iso[2:4]}" if iso else ""


def _date_cell(d) -> str:
    iso = _iso(d)
    return f"<span dir='ltr' data-iso='{iso}'>{_e(_fmt(d))}</span>" if iso else ""


COLLAPSE_TOP = 20
