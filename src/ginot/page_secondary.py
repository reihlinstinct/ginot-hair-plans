"""Secondary site pages: About, AI reviews, social metadata and Atom feed."""

from . import __version__
from .page_resources import _ANALYTICS_SNIPPET, _DATASETS_JS, _SOURCES_ROWS, _e


def render_about(generated: str, council_name: str) -> str:
    """Combined About + data-sources + datasets page (issue: datasets off the
    main page, owner request 2026-10-21). Generated with the site so the
    update stamp stays current; the datasets list loads from index.json."""
    rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(src)}</td><td>{_e(what)}</td>"
        f"<td>{_e(cad)}</td><td>{link}</td></tr>"
        for name, src, what, cad, link in _SOURCES_ROWS
    )
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>אודות ומקורות נתונים - {_e(council_name)}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="style.css">{_ANALYTICS_SNIPPET}</head><body>
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
<p>ספירת ביקורים: האתר משתמש ב-Cloudflare Web Analytics למדידת מספר ביקורים
בלבד, ללא עוגיות, ללא שמירת כתובות IP וללא מעקב אישי. טקסט חיפוש חופשי אינו
נשלח: הוא מוסר מכתובת העמוד לפני שהמדידה נשלחת.</p>
<p>סטטיסטיקת שימוש: האתר אוסף מונים מצטברים ואנונימיים על חיפושים ומסננים
(אילו תכניות, רחובות ומסננים מחפשים). חיפוש נספר רק כשהוא תואם בדיוק לערך
מהנתונים עצמם; טקסט חופשי לעולם אינו יוצא מהדפדפן. המונים פומביים ומוצגים
בסעיף "סטטיסטיקת שימוש" בעמוד זה.</p>
<h2>סטטיסטיקת שימוש</h2>
<p>מונים מצטברים ואנונימיים של חיפושים ומסננים באתר (30 יום אחרונים),
ישירות ממוני השרת הציבוריים.</p>
<div id="usage-stats">טוען…</div>
<script>(function(){{
var el=document.getElementById('usage-stats');if(!el)return;
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
fetch('https://ginot-hair-api.reihlinstinct.workers.dev/stats/summary').then(function(r){{return r.json();}}).then(function(d){{
  var NAMES={{search:'חיפושי תכניות',permits_search:'חיפושי בקשות',filter:'מסנני תכניות',permits_filter:'מסנני בקשות'}};
  var html='',any=false;
  Object.keys(NAMES).forEach(function(e){{
    var m=(d.events||{{}})[e];if(!m)return;
    var keys=Object.keys(m).slice(0,10);if(!keys.length)return;
    var items=keys.map(function(k){{
      // Defense in depth: render counts only as plain integers.
      var n=parseInt(m[k],10);
      return isFinite(n)&&n>=0?'<li>'+esc(k)+': '+n+'</li>':'';
    }}).join('');
    if(items){{any=true;html+='<h3>'+NAMES[e]+'</h3><ul>'+items+'</ul>';}}
  }});
  el.innerHTML=any?html:'<p>אין עדיין נתונים.</p>';
}}).catch(function(){{el.textContent='';}});
}})();</script>
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


def review_social_meta(pl_number, plan_name, base_url, has_image, early_intent=False):
    title = f"סקירת AI - {pl_number}" + (f" | {plan_name}" if plan_name else "")
    desc = (
        "נקודות לדיון מתוך מסמכי התכנית. סיכום אוטומטי, לא מסמך רשמי ולא ייעוץ מקצועי."
    )
    if early_intent:
        desc = (
            "הכנה מוקדמת בלבד מרישום ציבורי. לא נבדקה תכנית מפורטת; "
            "אין תחזית הפקדה. סיכום אוטומטי, לא מסמך רשמי ולא ייעוץ מקצועי."
        )
    tags = [
        ("property", "og:type", "article"),
        ("property", "og:locale", "he_IL"),
        ("property", "og:title", title),
        ("property", "og:description", desc),
        ("name", "description", desc),
        ("name", "twitter:title", title),
        ("name", "twitter:description", desc),
    ]
    if base_url:
        base = base_url.rstrip("/") + "/"
        tags.append(
            ("property", "og:url", base + f"reviews/talking_points_{pl_number}.html")
        )
        image = base + (f"reviews/og_{pl_number}.png" if has_image else "og.png")
        tags += [
            ("property", "og:image", image),
            ("property", "og:image:width", "1200"),
            ("property", "og:image:height", "630"),
            ("property", "og:image:type", "image/png"),
            ("property", "og:image:alt", title),
            ("name", "twitter:image", image),
            ("name", "twitter:card", "summary_large_image"),
        ]
    else:
        tags.append(("name", "twitter:card", "summary"))
    return "\n".join(
        f'<meta {key}="{name}" content="{_e(value)}">' for key, name, value in tags
    )


def render_review(
    pl_number: str,
    md_text: str,
    generated: str,
    council_name: str,
    base_url: str = "",
    plan_name: str = "",
    preview_image: bool = False,
    external_html: str = "",
) -> str:
    """Render a plan's AI talking-points markdown as a styled site page
    (issue #177). The .md stays the source of truth in the repo; the site
    render converts it - no separate Action. Clearly labelled AI content."""
    import markdown

    body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists"]
    )
    early_intent = "<!-- review-stage: early-intent -->" in md_text
    social = review_social_meta(
        pl_number, plan_name, base_url, preview_image, early_intent
    )
    basis = (
        "הכנה מוקדמת מרישום ציבורי בלבד; לא נבדקה תכנית מפורטת."
        if early_intent
        else "מתוך מסמכי התכנית הרשמיים."
    )
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
<link rel="stylesheet" href="../style.css">{_ANALYTICS_SNIPPET}</head><body>
<div class="ai-banner"><b>סקירת AI</b> - סיכום נקודות לדיון שהופק <b>אוטומטית באמצעות AI</b>
{basis} התוכן אינו מסמך רשמי ואינו תחליף לקריאתם במו"ת.</div>
<article class="review-body">
{body}
</article>
{external_html}
<p><a href="../index.html">חזרה לעמוד הראשי</a> &middot; עודכן: {_e(generated)}</p>
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת {_e(council_name)} - בלתי רשמי.
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
</body></html>"""


def render_feed(
    changes: list[dict], generated: str, council_name: str, base_url: str = ""
) -> str:
    entries = "".join(
        f"""<entry><title>{_e(c["kind"])}: {_e(c["pl_number"])} {_e(c["pl_name"])}</title>
<link href="{_e(c["mavat_url"])}"/><id>urn:ginot:{_e(c["pl_number"])}:{_e(c["kind"])}:{_e(generated)}</id>
<updated>{_e(generated)}T00:00:00Z</updated></entry>"""
        for c in changes
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="he">
<title>תכניות חדשות - {_e(council_name)}</title><id>{_e(base_url or "urn:ginot:feed")}</id>
<updated>{_e(generated)}T00:00:00Z</updated>{entries}</feed>"""
