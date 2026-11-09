"""On-demand plan-objection email endpoint (Vercel Python serverless function).

A visitor submits {email, plan_number, lang, subscribe} from the site's
email.html page; the function reads the plan's PUBLIC data from the site's
own published JSON and composes an email in the language of the page the
visitor used (he/en/ar/ru/am/fr; machine drafts except Hebrew). The email
carries the plan number/name, status, objection deadline, mavat link and a
how-to-object pointer, and is signed "reihlinstinct".

With subscribe=true the visitor gets a double opt-in confirmation email and,
once confirmed, a notification when the plan's objection deadline is within
7 days or its status changes (daily cron calls GET ?action=notify with the
CRON_SECRET bearer). One-click unsubscribe: GET ?action=unsubscribe&token=...
deletes the record immediately. Minimal data only: address, plan id,
language, tokens, timestamps. Nothing else is stored, shared or logged.

Storage is Vercel KV (Upstash Redis) via KV_REST_API_URL/KV_REST_API_TOKEN.
Without them the subscription paths are inert and the endpoint still sends
one-time emails. Pending confirmations expire after 48h.

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
import secrets
import smtplib
import time
import urllib.parse
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler

SITE_DATA_URL = os.environ.get(
    "SITE_DATA_URL",
    "https://reihlinstinct.github.io/ginot-hair-plans/data.json",
)
BASE_URL = os.environ.get("BASE_URL", "https://ginot-hair-plans.vercel.app")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
PER_IP_HOURLY_CAP = int(os.environ.get("PER_IP_HOURLY_CAP", "3"))
DAILY_SEND_CAP = int(os.environ.get("DAILY_SEND_CAP", "50"))
PENDING_TTL_SECONDS = 48 * 3600  # double opt-in records expire
NOTIFY_WINDOW_DAYS = 7

# Per-instance throttle state (documented limitation: resets on cold start).
_IP_HITS: dict[str, list[float]] = {}
_DAILY: dict[str, int] = {}

# Public-data cache (the dataset changes at most a few times a day).
_CACHE: dict = {"at": 0.0, "plans": {}}
_CACHE_TTL = 3600.0

LANGS = ("he", "en", "ar", "ru", "am", "fr")

# Email strings per language. Hebrew is the source of truth; the rest are
# machine drafts pending native-speaker review (tracked in issue #942).
# The signature is always the Latin "reihlinstinct" (owner request).
_STRINGS = {
    "he": {
        "subject": "תוכנית {number} - מועד אחרון להגשת התנגדות",
        "intro": "ביקשת עדכון על תוכנית {number} ({name}) באתר גינות העיר.",
        "status": "סטטוס: {status}",
        "deadline": "מועד אחרון להגשת התנגדות: {deadline}",
        "no_deadline": "מועד אחרון להגשת התנגדות: לא פורסם עדיין",
        "mavat": 'עמוד התוכנית במב"ת: {url}',
        "howto": "ההתנגדות מוגשת לוועדה המקומית לתכנון ובניה ירושלים, בדרך המקוונת "
        'דרך עמוד התוכנית במב"ת או לפי ההוראות בפרסום ההפקדה.',
        "disclaimer": "המידע נאסף ממקורות ציבוריים בלבד ואינו תחליף לייעוץ מקצועי.",
        "confirm_subject": "אישור הרשמה לעדכונים על תוכנית {number}",
        "confirm_intro": "כדי להשלים את ההרשמה לעדכונים על תוכנית {number}, "
        "יש לאשר בקישור: {url}",
        "confirm_expiry": "הקישור בתוקף 48 שעות. אם לא ביקשת הרשמה, אפשר להתעלם.",
        "unsub": "להסרה מרשימת העדכונים: {url}",
        "notify_status": "הסטטוס של תוכנית {number} השתנה: {status}",
        "notify_deadline": "המועד האחרון להתנגדות לתוכנית {number} מתקרב: {deadline}",
    },
    "en": {
        "subject": "Plan {number} - objection deadline",
        "intro": "You asked for an update on plan {number} ({name}) from the Ginot HaIr site.",
        "status": "Status: {status}",
        "deadline": "Objection deadline: {deadline}",
        "no_deadline": "Objection deadline: not published yet",
        "mavat": "Plan page on Mavat: {url}",
        "howto": "Objections are filed with the Jerusalem Local Planning and Building "
        "Committee, online via the plan's Mavat page or per the deposit notice.",
        "disclaimer": "Information collected from public sources only; not professional advice.",
        "confirm_subject": "Confirm subscription to plan {number} updates",
        "confirm_intro": "To confirm updates about plan {number}, open: {url}",
        "confirm_expiry": "The link is valid for 48 hours. If you did not subscribe, ignore this.",
        "unsub": "Unsubscribe: {url}",
        "notify_status": "The status of plan {number} changed: {status}",
        "notify_deadline": "The objection deadline for plan {number} is near: {deadline}",
    },
    "ar": {
        "subject": "الخطة {number} - الموعد الأخير لتقديم اعتراض",
        "intro": "طلبت تحديثًا حول الخطة {number} ({name}) من موقع غينوت هعير.",
        "status": "الحالة: {status}",
        "deadline": "الموعد الأخير لتقديم اعتراض: {deadline}",
        "no_deadline": "الموعد الأخير لتقديم اعتراض: لم يُنشر بعد",
        "mavat": "صفحة الخطة في مب\"ت: {url}",
        "howto": "تُقدَّم الاعتراضات إلى اللجنة المحلية للتخطيط والبناء في القدس، "
        "عبر الإنترنت من صفحة الخطة في مب\"ت أو وفقًا لإعلان الإيداع.",
        "disclaimer": "المعلومات مجموعة من مصادر عامة فقط وليست بديلاً عن استشارة مهنية.",
        "confirm_subject": "تأكيد الاشتراك في تحديثات الخطة {number}",
        "confirm_intro": "لتأكيد الاشتراك في تحديثات الخطة {number}، افتح: {url}",
        "confirm_expiry": "الرابط صالح لمدة 48 ساعة. إذا لم تطلب الاشتراك، تجاهل هذه الرسالة.",
        "unsub": "لإلغاء الاشتراك: {url}",
        "notify_status": "تغيّرت حالة الخطة {number}: {status}",
        "notify_deadline": "اقترب الموعد الأخير للاعتراض على الخطة {number}: {deadline}",
    },
    "ru": {
        "subject": "План {number} - крайний срок подачи возражения",
        "intro": "Вы запросили обновление по плану {number} ({name}) с сайта Гинот hа-Ир.",
        "status": "Статус: {status}",
        "deadline": "Крайний срок подачи возражения: {deadline}",
        "no_deadline": "Крайний срок подачи возражения: ещё не опубликован",
        "mavat": "Страница плана в Мават: {url}",
        "howto": "Возражения подаются в местную комиссию по планированию и строительству "
        "Иерусалима онлайн через страницу плана в Мават или по указаниям публикации.",
        "disclaimer": "Информация собрана только из открытых источников и не является "
        "профессиональной консультацией.",
        "confirm_subject": "Подтверждение подписки на обновления плана {number}",
        "confirm_intro": "Чтобы подтвердить подписку на обновления плана {number}, откройте: {url}",
        "confirm_expiry": "Ссылка действует 48 часов. Если вы не подписывались, проигнорируйте.",
        "unsub": "Отписаться: {url}",
        "notify_status": "Статус плана {number} изменился: {status}",
        "notify_deadline": "Приближается крайний срок возражения по плану {number}: {deadline}",
    },
    "am": {
        "subject": "ዕቅድ {number} - የተቃውሞ ማቅረቢያ የመጨረሻ ቀን",
        "intro": "ስለ ዕቅድ {number} ({name}) ከጊኖት ሃዒር ጣቢያ ዝመና ጠይቀዋል።",
        "status": "ሁኔታ: {status}",
        "deadline": "የተቃውሞ ማቅረቢያ የመጨረሻ ቀን: {deadline}",
        "no_deadline": "የተቃውሞ ማቅረቢያ የመጨረሻ ቀን: እስካሁን አልታተመም",
        "mavat": "የዕቅዱ ገጽ በማቫት: {url}",
        "howto": "ተቃውሞዎች ለየሩሳሌም የአካባቢ እቅድ እና ግንባታ ኮሚቴ በመስመር ላይ በማቫት ገጽ "
        "ወይም እንደ ማስታወቂያው መመሪያ ይቀርባሉ።",
        "disclaimer": "መረጃው ከሕዝባዊ ምንጮች ብቻ የተሰበሰበ ነው፤ የባለሙያ ምክር ተተኪ አይደለም።",
        "confirm_subject": "የዕቅድ {number} ዝመናዎች ምዝገባ አረጋግጥ",
        "confirm_intro": "የዕቅድ {number} ዝመናዎችን ለማረጋገጥ ይህን ይክፈቱ: {url}",
        "confirm_expiry": "አገናኙ ለ48 ሰዓታት ተቀባይነት አለው። ካልጠየቁ ይተውት።",
        "unsub": "ምዝገባ ማቋረጥ: {url}",
        "notify_status": "የዕቅድ {number} ሁኔታ ተቀይሯል: {status}",
        "notify_deadline": "የዕቅድ {number} የተቃውሞ ቀን ቀርቧል: {deadline}",
    },
    "fr": {
        "subject": "Plan {number} - date limite d'opposition",
        "intro": "Vous avez demandé une mise à jour sur le plan {number} ({name}) "
        "du site Ginot HaIr.",
        "status": "Statut : {status}",
        "deadline": "Date limite d'opposition : {deadline}",
        "no_deadline": "Date limite d'opposition : pas encore publiée",
        "mavat": "Page du plan sur Mavat : {url}",
        "howto": "Les oppositions se déposent auprès de la commission locale "
        "d'urbanisme de Jérusalem, en ligne via la page Mavat du plan ou selon "
        "l'avis de dépôt.",
        "disclaimer": "Informations issues uniquement de sources publiques ; "
        "ceci n'est pas un conseil professionnel.",
        "confirm_subject": "Confirmer l'abonnement aux mises à jour du plan {number}",
        "confirm_intro": "Pour confirmer les mises à jour du plan {number}, ouvrez : {url}",
        "confirm_expiry": "Le lien est valable 48 heures. Sans demande de votre part, ignorez.",
        "unsub": "Se désabonner : {url}",
        "notify_status": "Le statut du plan {number} a changé : {status}",
        "notify_deadline": "La date limite d'opposition au plan {number} approche : {deadline}",
    },
}
SIGNATURE = "reihlinstinct"


def _strings(lang: str) -> dict:
    return _STRINGS.get(lang) or _STRINGS["he"]


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


def plan_status(plan: dict) -> str:
    return plan.get("land_status") or plan.get("internet_short_status") or ""


def plan_deadline(plan: dict) -> str:
    return plan.get("objection_deadline_derived_2m_from_publication") or plan.get(
        "objection_deadline_derived_60d_from_publication"
    ) or plan.get("objection_deadline") or ""


# Section: subscription storage (Vercel KV / Upstash REST; inert when unset)

KV_URL = os.environ.get("KV_REST_API_URL", "")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")


def _kv(*args: str):
    """One Upstash REST command; returns the result field or None on failure
    or when storage is not configured (subscriptions stay inert)."""
    if not (KV_URL and KV_TOKEN):
        return None
    path = "/".join(urllib.parse.quote(a, safe="") for a in args)
    req = urllib.request.Request(
        f"{KV_URL}/{path}", headers={"Authorization": f"Bearer {KV_TOKEN}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("result")
    except Exception:  # noqa: BLE001 - storage failure must not break sending
        return None


def store_pending(token: str, record: dict) -> bool:
    ok = _kv("set", f"pending:{token}", json.dumps(record), "EX", str(PENDING_TTL_SECONDS))
    return ok == "OK"


def load_pending(token: str):
    raw = _kv("get", f"pending:{token}")
    return json.loads(raw) if raw else None


def confirm_pending(token: str) -> dict | None:
    record = load_pending(token)
    if not record:
        return None
    unsub = secrets.token_urlsafe(24)
    record["unsub_token"] = unsub
    record["confirmed_at"] = int(time.time())
    record["last_notified"] = ""
    if _kv("set", f"sub:{unsub}", json.dumps(record)) != "OK":
        return None
    _kv("sadd", f"plans:{record['plan']}", unsub)
    _kv("sadd", "plans", record["plan"])
    _kv("del", f"pending:{token}")
    return record


def unsubscribe(token: str) -> bool:
    raw = _kv("get", f"sub:{token}")
    if not raw:
        return False
    record = json.loads(raw)
    _kv("srem", f"plans:{record['plan']}", token)
    _kv("del", f"sub:{token}")
    return True


def iter_subscriptions():
    """Yield (unsub_token, record) for every confirmed subscriber."""
    plans = _kv("smembers", "plans") or []
    for plan in plans:
        for token in _kv("smembers", f"plans:{plan}") or []:
            raw = _kv("get", f"sub:{token}")
            if raw:
                yield token, json.loads(raw)


def save_subscription(token: str, record: dict) -> None:
    _kv("set", f"sub:{token}", json.dumps(record))


# Section: email composition and sending


def _message(subject: str, lines: list[str], to_addr: str) -> MIMEText:
    lines += ["", SIGNATURE]
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


def compose(plan: dict, to_addr: str, lang: str = "he", unsub_token: str = "") -> MIMEText:
    """The public plan facts as an email in the page's language. Nothing
    about the recipient is logged; the address only enters the To header."""
    s = _strings(lang)
    number = plan.get("pl_number", "")
    name = plan.get("pl_name") or ""
    deadline = plan_deadline(plan)
    lines = [
        s["intro"].format(number=number, name=name),
        "",
        s["status"].format(status=plan_status(plan)),
        s["deadline"].format(deadline=deadline) if deadline else s["no_deadline"],
        "",
    ]
    mavat = plan.get("mavat_url") or ""
    if mavat:
        lines += [s["mavat"].format(url=mavat), ""]
    lines += [s["howto"], "", s["disclaimer"]]
    if unsub_token:
        url = f"{BASE_URL}/api/send_plan_email?action=unsubscribe&token={unsub_token}"
        lines += ["", s["unsub"].format(url=url)]
    return _message(s["subject"].format(number=number), lines, to_addr)


def compose_confirm(record: dict, token: str) -> MIMEText:
    """Double opt-in: the confirmation email in the subscriber's language."""
    s = _strings(record.get("lang", "he"))
    url = f"{BASE_URL}/api/send_plan_email?action=confirm&token={token}"
    lines = [
        s["confirm_intro"].format(number=record["plan"], url=url),
        "",
        s["confirm_expiry"],
    ]
    return _message(s["confirm_subject"].format(number=record["plan"]), lines, record["email"])


def compose_notify(record: dict, reason: str) -> MIMEText:
    """The subscription notification (status change / deadline near)."""
    s = _strings(record.get("lang", "he"))
    plan = record["plan"]
    lines = [reason, ""]
    lines += [
        s["unsub"].format(
            url=f"{BASE_URL}/api/send_plan_email?action=unsubscribe&token={record['unsub_token']}"
        )
    ]
    return _message(s["subject"].format(number=plan), lines, record["email"])


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


def _subscription_notices(plans: dict) -> list[tuple[dict, str]]:
    """(record, reason) for subscribers due a notification."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    out = []
    for token, record in iter_subscriptions():
        plan = plans.get(record.get("plan", ""))
        if not plan:
            continue
        record["unsub_token"] = token
        status = plan_status(plan)
        deadline = plan_deadline(plan)
        marker = f"{status}|{deadline}|{today}"
        if record.get("last_notified") == marker:
            continue
        s = _strings(record.get("lang", "he"))
        if status and status != record.get("status"):
            reason = s["notify_status"].format(number=record["plan"], status=status)
        elif deadline and 0 <= _days_until(deadline) <= NOTIFY_WINDOW_DAYS:
            reason = s["notify_deadline"].format(number=record["plan"], deadline=deadline)
        else:
            record["status"] = status
            record["last_notified"] = marker
            save_subscription(token, record)
            continue
        record["status"] = status
        record["last_notified"] = marker
        out.append((record, reason))
    return out


def _days_until(iso_date: str) -> int:
    """Whole days from today (UTC) to the YYYY-MM-DD date; -1 when unparseable."""
    import datetime

    try:
        then = datetime.date.fromisoformat(iso_date[:10])
    except ValueError:
        return -1
    return (then - datetime.datetime.now(datetime.timezone.utc).date()).days


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

    def _reply_html(self, code: int, text: str) -> None:
        payload = (
            "<!DOCTYPE html><html><body><p>" + text + "</p></body></html>"
        ).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _query(self) -> dict:
        from urllib.parse import parse_qs, urlparse

        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def do_OPTIONS(self) -> None:  # CORS preflight
        self._reply(204, {})

    def do_GET(self) -> None:
        q = self._query()
        action = q.get("action", "")
        if action == "confirm":
            record = confirm_pending(q.get("token", ""))
            return self._reply_html(200 if record else 400, "OK" if record else "Invalid")
        if action == "unsubscribe":
            return self._reply_html(
                200 if unsubscribe(q.get("token", "")) else 400, "OK"
            )
        if action == "notify":
            secret = os.environ.get("CRON_SECRET", "")
            auth = self.headers.get("Authorization", "")
            if not secret or auth != f"Bearer {secret}":
                return self._reply(403, {"ok": False})
            sent = 0
            try:
                notices = _subscription_notices(load_plans())
                for record, reason in notices:
                    send(compose_notify(record, reason), record["email"])
                    save_subscription(record["unsub_token"], record)
                    sent += 1
            except Exception:  # noqa: BLE001 - generic 502, never leak internals
                return self._reply(502, {"ok": False})
            return self._reply(200, {"ok": True, "sent": sent})
        return self._reply(404, {"ok": False})

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
        lang = str(body.get("lang", "he")).strip()
        if lang not in LANGS:
            lang = "he"
        subscribe = bool(body.get("subscribe"))
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
            send(compose(plan, email, lang), email)
            if subscribe:
                token = secrets.token_urlsafe(24)
                record = {"email": email, "plan": plan_number, "lang": lang,
                          "created": int(time.time()), "status": plan_status(plan)}
                if store_pending(token, record):
                    send(compose_confirm(record, token), email)
        except Exception:  # noqa: BLE001 - generic 502, never leak internals
            return self._reply(502, {"ok": False})
        _record_send(ip)
        return self._reply(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:  # no request logging
        pass
