"""Email-request page: a public form asking for the plan objection email.

Generated with the site so the update stamp and the open-objection plan list
stay current. The form posts to the on-demand email function (api/, see
api/README.md); the endpoint URL lives in EMAIL_ENDPOINT below - the one
place to update when the function is deployed. Sender account settings are
NOT here: they are Vercel env vars documented in api/README.md.
"""

from . import __version__
from .page_resources import _ANALYTICS_SNIPPET, _e

# The one documented place for the function URL (api/README.md explains).
EMAIL_ENDPOINT = "https://REPLACE-WITH-VERCEL-URL.vercel.app/api/send_plan_email"


def render_email_page(rows: list[dict], generated: str, council_name: str) -> str:
    """The form page, listing plans whose objection window is still open."""
    open_rows = [r for r in rows if r.get("_open_obj")]
    options = "".join(
        f'<option value="{_e(r.get("pl_number") or "")}">'
        f'{_e(r.get("pl_number") or "")} - {_e(r.get("pl_name") or "")}</option>'
        for r in open_rows
    )
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>קבלת מייל על תוכנית - {_e(council_name)}</title>
<link rel="icon" type="image/x-icon" sizes="16x16 32x32 48x48" href="favicon.ico?v=20261022">
<link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg?v=20261022">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v=20261022">
<link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261022">
<meta name="theme-color" content="#101f5b">
<link rel="stylesheet" href="style.css">{_ANALYTICS_SNIPPET}</head><body>
<h1>קבלת מייל על תוכנית</h1>
<p>בחרו תוכנית בהפקדה וקבלו מייל חד-פעמי עם פרטי התוכנית, המועד האחרון
להגשת התנגדות וקישור לעמוד התוכנית במב"ת. כתובת המייל משמשת לשליחה בלבד
ואינה נשמרת. עודכן: {_e(generated)}.</p>
<form id="email-form" method="post" action="#">
<p><label>תוכנית:<br>
<select id="plan" name="plan_number" required>{options}</select></label></p>
<p><label>כתובת מייל:<br>
<input type="email" id="email" name="email" required size="30"
 autocomplete="email" dir="ltr"></label></p>
<p style="display:none" aria-hidden="true"><label>אתר:
<input type="text" id="website" name="website" tabindex="-1"
 autocomplete="off"></label></p>
<p><button type="submit">שלחו לי מייל</button></p>
<p id="form-status" role="status"></p>
</form>
<script>
(function(){{
var form=document.getElementById('email-form'),st=document.getElementById('form-status');
form.addEventListener('submit',function(ev){{
ev.preventDefault();st.textContent='שולח...';
fetch('{EMAIL_ENDPOINT}',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{email:form.email.value,plan_number:form.plan_number.value,
website:form.website.value}})}}).then(function(r){{
st.textContent=r.ok?'אם הכתובת תקינה, המייל בדרך.':'לא ניתן לשלוח כרגע, נסו מאוחר יותר.';
}}).catch(function(){{st.textContent='לא ניתן לשלוח כרגע, נסו מאוחר יותר.';}});
}});
}})();
</script>
<footer dir="rtl"><p>
אתר נתונים אוטומטי של ועדת גינות העיר.
<a href="index.html">חזרה לעמוד הראשי</a>
</p><p class="site-version">גרסה <span dir="ltr">{__version__}</span> · Version {__version__}</p></footer>
</body></html>"""
