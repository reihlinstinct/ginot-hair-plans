"""Email-request page: a public form asking for the plan objection email.

Generated with the site so the update stamp and the open-objection plan list
stay current. The form posts to the on-demand email function (api/, see
api/README.md); the endpoint URL lives in EMAIL_ENDPOINT below - the one
place to update when the function is deployed. Sender account settings are
NOT here: they are Vercel env vars documented in api/README.md.
"""

import json

from . import __version__, i18n
from .page_resources import _ANALYTICS_SNIPPET, _e

# The one documented place for the function URL (api/README.md explains).
EMAIL_ENDPOINT = "https://ginot-hair-plans.vercel.app/api/send_plan_email"


def _js(text: str) -> str:
    """A string literal safe inside a script element."""
    return json.dumps(text, ensure_ascii=False).replace("</", "<\\/")


def render_email_page(
    rows: list[dict], generated: str, council_name: str, lang: str | None = None
) -> str:
    """The form page, listing plans whose objection window is still open.

    lang defaults to the document's default language; every label, the
    direction and the language selector come from i18n/strings.json."""
    lang = lang or i18n.default_lang()
    t = lambda key, **kw: i18n.t(lang, key, **kw)
    m = i18n.meta(lang)
    pre = i18n.asset_prefix(lang)
    open_rows = [r for r in rows if r.get("_open_obj")]
    options = "".join(
        f'<option value="{_e(r.get("pl_number") or "")}">'
        f"{_e(r.get('pl_number') or '')} - {_e(r.get('pl_name') or '')}</option>"
        for r in open_rows
    )
    draft = (
        f'<p class="draft-note" lang="{_e(m["lang"])}">{_e(t("ui.draft_note"))}</p>'
        if i18n.is_draft(lang)
        else ""
    )
    return f"""<!DOCTYPE html>
<html dir="{m["dir"]}" lang="{m["lang"]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(t("email.title"))} - {_e(council_name)}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="{pre}favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="{pre}favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="{pre}favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="{pre}apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="{pre}style.css">
<style>#email-form select,#email-form input[type=email]{{width:100%;max-width:100%;
box-sizing:border-box;font-size:16px;min-height:44px}}
#email-form button{{font-size:16px;min-height:44px;padding:0 20px}}
#email-form label{{display:block}}
#email-form input[type=email]{{direction:ltr;text-align:left}}</style>{_ANALYTICS_SNIPPET}</head><body>
{i18n.switcher(lang, "email.html")}
<h1>{_e(t("email.title"))}</h1>
{draft}<p>{_e(t("email.intro", generated=generated))}</p>
<form id="email-form" method="post" action="#">
<p><label>{_e(t("email.plan_label"))}<br>
<select id="plan" name="plan_number" required>{options}</select></label></p>
<p><label>{_e(t("email.email_label"))}<br>
<input type="email" id="email" name="email" required size="30"
 autocomplete="email" dir="ltr"></label></p>
<p><label><input type="checkbox" id="subscribe" name="subscribe">
{_e(t("email.subscribe"))}</label></p>
<input type="hidden" id="lang" name="lang" value="{_e(lang)}">
<p style="display:none" aria-hidden="true"><label>{_e(t("email.honeypot"))}
<input type="text" id="website" name="website" tabindex="-1"
 autocomplete="off"></label></p>
<p><button type="submit">{_e(t("email.submit"))}</button></p>
<p id="form-status" role="status"></p>
</form>
<script>
(function(){{
var form=document.getElementById('email-form'),st=document.getElementById('form-status');
var want=new URLSearchParams(location.search).get('plan');
if(want){{Array.prototype.forEach.call(form.plan_number.options,function(o){{if(o.value===want){{form.plan_number.value=want;}}}});}}
form.addEventListener('submit',function(ev){{
ev.preventDefault();st.textContent={_js(t("email.sending"))};
fetch('{EMAIL_ENDPOINT}',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{email:form.email.value,plan_number:form.plan_number.value,
lang:form.lang.value,subscribe:form.subscribe.checked,
website:form.website.value}})}}).then(function(r){{
st.textContent=r.ok?{_js(t("email.ok"))}:{_js(t("email.error"))};
}}).catch(function(){{st.textContent={_js(t("email.error"))};}});
}});
}})();
</script>
<footer dir="{m["dir"]}"><p>
{_e(t("ui.site_footer"))}
<a href="{pre}index.html">{_e(t("ui.back_home"))}</a>
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
</body></html>"""
