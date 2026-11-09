"""On-demand plan-objection email endpoint (Vercel Python serverless function).

A visitor submits {email, plan_number} from the site's email.html page; the
function reads the plan's PUBLIC data from the site's own published JSON,
composes a Hebrew email (plan number/name, status, objection deadline with
the statutory 2-month date, mavat link, how-to-object pointer) and sends it
via SMTP. No database: the recipient address is used in memory to send and
is never logged or stored.

Sender account is fully env-driven (one documented swap place, no code
change): SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / EMAIL_FROM_ADDRESS
/ EMAIL_FROM_NAME / EMAIL_REPLY_TO. See api/README.md.

Abuse protection (public form): honeypot field (silent fake success),
per-IP hourly throttle and a global daily cap. Both throttles are per
serverless instance (in-memory) - Gmail's own ~500/day SMTP cap is the hard
backstop. Cloudflare Turnstile can be added behind REQUIRE_TURNSTILE later.

Stdlib only; the Vercel Python runtime serves the `handler` class.
"""

import json
import os
import smtplib
import time
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler

SITE_DATA_URL = os.environ.get(
    "SITE_DATA_URL",
    "https://reihlinstinct.github.io/ginot-hair-plans/data.json",
)
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
PER_IP_HOURLY_CAP = int(os.environ.get("PER_IP_HOURLY_CAP", "3"))
DAILY_SEND_CAP = int(os.environ.get("DAILY_SEND_CAP", "50"))

# Per-instance throttle state (documented limitation: resets on cold start).
_IP_HITS: dict[str, list[float]] = {}
_DAILY: dict[str, int] = {}

# Public-data cache (the dataset changes at most a few times a day).
_CACHE: dict = {"at": 0.0, "plans": {}}
_CACHE_TTL = 3600.0


def load_plans() -> dict:
    """plan_number -> row, from the site's published public JSON."""
    now = time.time()
    if now - _CACHE["at"] < _CACHE_TTL and _CACHE["plans"]:
        return _CACHE["plans"]
    with urllib.request.urlopen(SITE_DATA_URL, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows = data.get("rows", data) if isinstance(data, dict) else data
    plans = {}
    for row in rows:
        if isinstance(row, dict) and row.get("pl_number"):
            plans[row["pl_number"]] = row
    _CACHE.update(at=now, plans=plans)
    return plans


def _throttled(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _IP_HITS.get(ip, []) if now - t < 3600]
    _IP_HITS[ip] = hits
    if len(hits) >= PER_IP_HOURLY_CAP:
        return True
    today = time.strftime("%Y-%m-%d", time.gmtime(now))
    return _DAILY.get(today, 0) >= DAILY_SEND_CAP


def _record_send(ip: str) -> None:
    _IP_HITS.setdefault(ip, []).append(time.time())
    today = time.strftime("%Y-%m-%d", time.gmtime())
    _DAILY[today] = _DAILY.get(today, 0) + 1


def compose(plan: dict, to_addr: str) -> MIMEText:
    """The public plan facts as a Hebrew email. Nothing about the recipient
    is logged; the address only enters the To header of the sent message."""
    number = plan.get("pl_number", "")
    name = plan.get("pl_name") or ""
    status = plan.get("land_status") or plan.get("internet_short_status") or ""
    deadline = plan.get("objection_deadline_derived_2m_from_publication") or plan.get(
        "objection_deadline_derived_60d_from_publication"
    ) or plan.get("objection_deadline") or ""
    mavat = plan.get("mavat_url") or ""
    subject = f"תוכנית {number} - מועד אחרון להגשת התנגדות"
    lines = [
        "שלום,",
        "",
        f"ביקשת עדכון על תוכנית {number} ({name}) באתר גינות העיר.",
        "",
        f"סטטוס: {status}",
        f"מועד אחרון להגשת התנגדות: {deadline or 'לא פורסם עדיין'}",
        "",
    ]
    if mavat:
        lines += [f"עמוד התוכנית במב\"ת: {mavat}", ""]
    lines += [
        "ההתנגדות מוגשת לוועדה המקומית לתכנון ובניה ירושלים, בדרך המקוונת",
        "דרך עמוד התוכנית במב\"ת או לפי ההוראות בפרסום ההפקדה.",
        "",
        "המידע נאסף ממקורות ציבוריים בלבד ואינו תחליף לייעוץ מקצועי.",
        "reihlinstinct",
    ]
    msg = MIMEText("\n".join(lines), "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(
        (
            str(Header(os.environ.get("EMAIL_FROM_NAME", "reihlinstinct"), "utf-8")),
            os.environ.get("EMAIL_FROM_ADDRESS", os.environ.get("SMTP_USER", "")),
        )
    )
    reply_to = os.environ.get("EMAIL_REPLY_TO", "reihlinstinct@gmail.com")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["To"] = to_addr
    return msg


def send(msg: MIMEText, to_addr: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg, from_addr=user, to_addrs=[to_addr])


def _valid_email(addr: str) -> bool:
    if not addr or len(addr) > 254 or "@" not in addr:
        return False
    local, _, domain = addr.rpartition("@")
    return bool(local) and "." in domain and " " not in addr


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:  # CORS preflight
        self._reply(204, {})

    def do_POST(self) -> None:
        # Generic responses only: no oracle on plan existence or send state.
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 4096:
                return self._reply(400, {"ok": False})
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._reply(400, {"ok": False})

        # Honeypot: bots that fill the hidden field get a fake success.
        if body.get("website"):
            return self._reply(200, {"ok": True})

        email = str(body.get("email", "")).strip()
        plan_number = str(body.get("plan_number", "")).strip()
        if not _valid_email(email) or not plan_number:
            return self._reply(400, {"ok": False})

        ip = self.headers.get("x-forwarded-for", self.client_address[0]).split(",")[0].strip()
        if _throttled(ip):
            return self._reply(429, {"ok": False})

        try:
            plan = load_plans().get(plan_number)
        except Exception:  # noqa: BLE001 - generic 502, never leak internals
            return self._reply(502, {"ok": False})
        if not plan:
            return self._reply(400, {"ok": False})

        try:
            send(compose(plan, email), email)
        except Exception:  # noqa: BLE001 - generic 502, never leak internals
            return self._reply(502, {"ok": False})
        _record_send(ip)
        return self._reply(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:  # no request logging
        pass
