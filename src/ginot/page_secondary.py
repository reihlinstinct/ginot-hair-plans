"""Secondary site pages: About, AI reviews, social metadata and Atom feed."""

from . import __version__
from . import i18n as _i18n
from .page_resources import _ANALYTICS_SNIPPET, _datasets_js, _e, _sources_rows


def render_about(generated: str, council_name: str, lang: str = "he") -> str:
    """Combined About + data-sources + datasets page (issue: datasets off the
    main page, owner request 2026-10-21). Generated with the site so the
    update stamp stays current; the datasets list loads from index.json."""
    import json as _json

    meta = _i18n.meta(lang)
    pre = _i18n.asset_prefix(lang)

    def _t(key: str, **fmt) -> str:
        return _i18n.t(lang, key, **fmt)

    def J(key: str) -> str:
        return _json.dumps(_t(key), ensure_ascii=False)

    rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(src)}</td><td>{_e(what)}</td>"
        f"<td>{_e(cad)}</td><td>{link}</td></tr>"
        for name, src, what, cad, link in _sources_rows(lang, pre)
    )
    return f"""<!DOCTYPE html>
<html dir="{meta["dir"]}" lang="{meta["lang"]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(_t("about.title", council=council_name))}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="{pre}favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="{pre}favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="{pre}favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="{pre}apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="{pre}style.css">{_ANALYTICS_SNIPPET}</head><body>
{_i18n.switcher(lang, "about.html")}
<h1>{_e(_t("about.h1"))}</h1>
<p>{_t("about.intro_html", council=council_name, generated=generated)}</p>
{_i18n.draft_note(lang)}
<div class="ai-banner">{_t("about.banner_html")}</div>
<h2>{_e(_t("about.sources_h"))}</h2>
<table id="plans"><thead><tr><th>{_e(_t("about.col_dataset"))}</th><th>{_e(_t("about.col_source"))}</th><th>{_e(_t("about.col_what"))}</th><th>{_e(_t("about.col_cadence"))}</th><th>{_e(_t("about.col_links"))}</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>{_e(_t("about.datasets_h"))}</h2>
<ul id="datasets-list"><li>{_e(_t("about.loading_list"))}</li></ul>
<h2>{_e(_t("about.api_h"))}</h2>
<p>{_e(_t("about.api_intro"))}</p>
<table id="plans"><thead><tr><th>{_e(_t("about.col_file"))}</th><th>{_e(_t("about.col_content"))}</th><th>{_e(_t("about.col_structure"))}</th></tr></thead><tbody>
<tr><td><a href="{pre}data.json">data.json</a></td><td>{_e(_t("about.data_json_desc"))}</td>
<td>{{generated, rows[], changes[], permits[]}} - {_e(_t("about.data_json_struct"))}</td></tr>
<tr><td><a href="{pre}open.json">open.json</a></td><td>{_e(_t("about.open_json_desc"))}</td>
<td>{{generated, definition, count, plans[]}} - {_e(_t("about.open_json_struct"))}</td></tr>
<tr><td><a href="{pre}feed.xml">feed.xml</a></td><td>{_e(_t("about.feed_desc"))}</td><td>Atom 1.0</td></tr>
<tr><td><a href="{pre}badge/plans.json">badge/*.json</a></td><td>{_e(_t("about.badge_desc"))}</td>
<td>{{schemaVersion, label, message, color}}</td></tr>
<tr><td><a href="https://ginot-hair-api.reihlinstinct.workers.dev">ginot-hair-api.reihlinstinct.workers.dev</a></td>
<td>{_e(_t("about.api_desc"))}</td>
<td>{_e(_t("about.api_struct"))}</td></tr>
</tbody></table>
<h2>{_e(_t("about.privacy_h"))}</h2>
<p>{_e(_t("about.privacy1"))}</p>
<p>{_e(_t("about.privacy2"))}</p>
<p>{_e(_t("about.privacy3"))}</p>
<h2>{_e(_t("about.usage_h"))}</h2>
<p>{_e(_t("about.usage_intro"))}</p>
<div id="usage-stats">{_e(_t("about.usage_loading"))}</div>
<script>(function(){{
var el=document.getElementById('usage-stats');if(!el)return;
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
fetch('https://ginot-hair-api.reihlinstinct.workers.dev/stats/summary').then(function(r){{return r.json();}}).then(function(d){{
  var NAMES={{search:{J("us.search")},permits_search:{J("us.permits_search")},filter:{J("us.filter")},permits_filter:{J("us.permits_filter")}}};
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
  el.innerHTML=any?html:'<p>'+{J("about.usage_empty")}+'</p>';
}}).catch(function(){{el.textContent='';}});
}})();</script>
<h2>{_e(_t("about.code_h"))}</h2>
<p>{_e(_t("about.code_open"))}
<a href="https://github.com/reihlinstinct/ginot-hair-plans">GitHub</a>.
{_e(_t("about.code_help"))} <a href="https://github.com/reihlinstinct/ginot-hair-plans/blob/main/CONTRIBUTING.md">{_e(_t("index.footer_contrib"))}</a>.</p>
<p><a href="{pre}{_i18n.page_path(lang, "index.html")}">{_e(_t("ui.back_home"))}</a></p>
<footer dir="{meta["dir"]}"><p>
{_e(_t("about.footer_html", council=council_name))}
<a href="{pre}{_i18n.page_path(lang, "accessibility.html")}">{_e(_t("index.footer_a11y"))}</a>
</p><p class="site-version">{_e(_t("index.version"))} <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
<script>{_datasets_js(lang, pre)}</script>
</body></html>"""


def render_accessibility(generated: str, council_name: str, lang: str = "he") -> str:
    """On-site accessibility statement (SI 5568 regulation 35): standard target,
    measures, known limitations and the feedback channel. Generated with the
    site so the update stamp stays current."""
    meta = _i18n.meta(lang)
    pre = _i18n.asset_prefix(lang)

    def _t(key: str, **fmt) -> str:
        return _i18n.t(lang, key, **fmt)

    return f"""<!DOCTYPE html>
<html dir="{meta["dir"]}" lang="{meta["lang"]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(_t("a11y.title", council=council_name))}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="{pre}favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="{pre}favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="{pre}favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="{pre}apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="{pre}style.css">{_ANALYTICS_SNIPPET}</head><body>
{_i18n.switcher(lang, "accessibility.html")}
<h1>{_e(_t("a11y.h1"))}</h1>
<p>{_t("a11y.intro_html", council=council_name)}</p>
{_i18n.draft_note(lang)}
<h2>{_e(_t("a11y.measures_h"))}</h2>
{_t("a11y.measures_html")}
<h2>{_e(_t("a11y.limits_h"))}</h2>
{_t("a11y.limits_html")}
<h2>{_e(_t("a11y.contact_h"))}</h2>
<p>{_t("a11y.contact_html")}</p>
<p>{_t("a11y.updated", updated=generated)}</p>
<p><a href="{pre}{_i18n.page_path(lang, "index.html")}">{_e(_t("ui.back_home"))}</a></p>
<footer dir="{meta["dir"]}"><p class="site-version">{_e(_t("index.version"))} <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
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
