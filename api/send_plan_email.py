"""On-demand plan-objection email endpoint (Vercel Python serverless function).

A visitor submits {email, plan_number, lang, subscribe} from the site's
email.html page. Nothing is sent to the typed address until its owner
confirms: the function stores a pending record (48h expiry) and sends ONE
confirmation email; the link opens a page with a button, and only the
button's POST (never a GET, so link scanners cannot trigger it) sends the
plan email, composed in the page's language (he/en/ar/ru/am/fr; machine
drafts except Hebrew), signed "reihlinstinct". With subscribe=true the same
confirmation also creates a subscription: a notification when the plan's
objection deadline is within 7 days (once per deadline) or its status
changes (daily Vercel cron calls GET ?action=notify with the CRON_SECRET
bearer). A scope=all request subscribes to the whole polygon instead: one
daily digest when new plans appear in the dataset, with plans deposited for
objections highlighted (stored as plan "*"; the first cron run seeds the
known-plan set silently so nobody gets the backlog). Unsubscribe is a page with a POST button, plus RFC 8058
List-Unsubscribe-Post one-click headers on every subscriber email; it deletes
the record immediately. Minimal data only: address, plan id, language,
tokens, timestamps. Nothing else is stored, shared or logged.

Storage is Vercel KV (Upstash Redis) via KV_REST_API_URL/KV_REST_API_TOKEN;
without it the endpoint refuses requests (503) rather than sending
unconfirmed mail. Abuse protection: honeypot (silent fake success), strict
address check, confirm-before-send, and KV-backed counters (atomic INCR):
per-IP hourly, per-recipient daily and a global daily cap, counting every
message sent. Gmail's own ~500/day SMTP cap is the last backstop.

Sender account is fully env-driven (one documented swap place, no code
change): SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / EMAIL_FROM_ADDRESS
/ EMAIL_FROM_NAME / EMAIL_REPLY_TO. See api/README.md.

Stdlib only; the Vercel Python runtime serves the `handler` class.
"""

import functools
import hashlib
import hmac
import html
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
from pathlib import Path

SITE_DATA_URL = os.environ.get(
    "SITE_DATA_URL",
    "https://reihlinstinct.github.io/ginot-hair-plans/data.json",
)
BASE_URL = os.environ.get("BASE_URL", "https://ginot-hair-plans.vercel.app")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://reihlinstinct.github.io")
PER_IP_HOURLY_CAP = int(os.environ.get("PER_IP_HOURLY_CAP", "3"))
PER_RECIPIENT_DAILY_CAP = int(os.environ.get("PER_RECIPIENT_DAILY_CAP", "3"))
DAILY_SEND_CAP = int(os.environ.get("DAILY_SEND_CAP", "50"))
PENDING_TTL_SECONDS = 48 * 3600  # double opt-in records expire
NOTIFY_WINDOW_DAYS = 7
ALL_SCOPE = "*"  # plan value of a whole-polygon subscription
KNOWN_PLANS_KEY = "state:known_plans"  # JSON list seeded on first cron run

# In-memory counter fallback, used only when KV answers nothing (storage
# outage); the normal path counts in KV so every instance shares one count.
_DAILY: dict[str, int] = {}

# Public-data cache (the dataset changes at most a few times a day).
_CACHE: dict = {"at": 0.0, "plans": {}}
_CACHE_TTL = 3600.0


def _languages() -> tuple:
    """Language codes from the single strings document (the same file the
    site generator reads), so a language added there is accepted here."""
    path = Path(__file__).resolve().parent.parent / "src/ginot/i18n/strings.json"
    # No silent fallback: if the document did not ship, fail loudly.
    return tuple(json.loads(path.read_text(encoding="utf-8"))["languages"])


LANGS = _languages()

# Email strings per language. Hebrew is the source of truth; the rest are
# machine drafts pending native-speaker review (tracked in issue #942).
# The signature is always the Latin "reihlinstinct" (owner request).
_STRINGS = {
    "he": {
        "all_confirm_subject": "אישור הרשמה לעדכונים על תוכניות חדשות בגינות העיר",
        "all_confirm_intro": "כדי להשלים את ההרשמה לעדכונים על כל תוכנית חדשה "
        "בפוליגון גינות העיר, יש לאשר בקישור: {url}",
        "all_welcome_subject": "נרשמת לעדכונים על תוכניות חדשות בגינות העיר",
        "all_welcome_intro": "ההרשמה אושרה. כשתוכנית חדשה תכנס לפוליגון גינות העיר "
        "({count} תוכניות במעקב כרגע), יישלח עדכון יומי אחד; תוכניות שהופקדו "
        "להתנגדויות יודגשו.",
        "all_digest_subject": "תוכניות חדשות בגינות העיר",
        "all_digest_intro": "נכנסו {count} תוכניות חדשות לפוליגון גינות העיר:",
        "all_deposited_header": "מופקדות להתנגדויות:",
        "all_new_header": "תוכניות חדשות נוספות:",
        "all_item": "{number} - {name}",
        "all_item_status": "סטטוס: {status}",
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
        "all_confirm_subject": "Confirm subscription to new-plan updates for Ginot HaIr",
        "all_confirm_intro": "To confirm updates about every new plan in the "
        "Ginot HaIr polygon, open: {url}",
        "all_welcome_subject": "Subscribed to new-plan updates for Ginot HaIr",
        "all_welcome_intro": "Subscription confirmed. When a new plan enters the "
        "Ginot HaIr polygon ({count} plans tracked now), you will get one daily "
        "update; plans deposited for objections are highlighted.",
        "all_digest_subject": "New plans in Ginot HaIr",
        "all_digest_intro": "{count} new plans entered the Ginot HaIr polygon:",
        "all_deposited_header": "Deposited for objections:",
        "all_new_header": "Other new plans:",
        "all_item": "{number} - {name}",
        "all_item_status": "Status: {status}",
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
        "all_confirm_subject": "تأكيد الاشتراك في تحديثات الخطط الجديدة في غينوت هعير",
        "all_confirm_intro": "لتأكيد التحديثات حول كل خطة جديدة في مضلع غينوت هعير، "
        "افتح: {url}",
        "all_welcome_subject": "تم الاشتراك في تحديثات الخطط الجديدة في غينوت هعير",
        "all_welcome_intro": "تم تأكيد الاشتراك. عند دخول خطة جديدة إلى مضلع غينوت "
        "هعير ({count} خطة قيد المتابعة الآن)، ستصلك رسالة يومية واحدة؛ وتُبرز "
        "الخطط المودعة للاعتراضات.",
        "all_digest_subject": "خطط جديدة في غينوت هعير",
        "all_digest_intro": "دخلت {count} خطط جديدة إلى مضلع غينوت هعير:",
        "all_deposited_header": "مودعة للاعتراضات:",
        "all_new_header": "خطط جديدة أخرى:",
        "all_item": "{number} - {name}",
        "all_item_status": "الحالة: {status}",
        "subject": "الخطة {number} - الموعد الأخير لتقديم اعتراض",
        "intro": "طلبت تحديثًا حول الخطة {number} ({name}) من موقع غينوت هعير.",
        "status": "الحالة: {status}",
        "deadline": "الموعد الأخير لتقديم اعتراض: {deadline}",
        "no_deadline": "الموعد الأخير لتقديم اعتراض: لم يُنشر بعد",
        "mavat": 'صفحة الخطة في مب"ت: {url}',
        "howto": "تُقدَّم الاعتراضات إلى اللجنة المحلية للتخطيط والبناء في القدس، "
        'عبر الإنترنت من صفحة الخطة في مب"ت أو وفقًا لإعلان الإيداع.',
        "disclaimer": "المعلومات مجموعة من مصادر عامة فقط وليست بديلاً عن استشارة مهنية.",
        "confirm_subject": "تأكيد الاشتراك في تحديثات الخطة {number}",
        "confirm_intro": "لتأكيد الاشتراك في تحديثات الخطة {number}، افتح: {url}",
        "confirm_expiry": "الرابط صالح لمدة 48 ساعة. إذا لم تطلب الاشتراك، تجاهل هذه الرسالة.",
        "unsub": "لإلغاء الاشتراك: {url}",
        "notify_status": "تغيّرت حالة الخطة {number}: {status}",
        "notify_deadline": "اقترب الموعد الأخير للاعتراض على الخطة {number}: {deadline}",
    },
    "ru": {
        "all_confirm_subject": "Подтверждение подписки на новые планы Гинот hа-Ир",
        "all_confirm_intro": "Чтобы подтвердить обновления о каждом новом плане "
        "в полигоне Гинот hа-Ир, откройте: {url}",
        "all_welcome_subject": "Подписка на новые планы Гинот hа-Ир оформлена",
        "all_welcome_intro": "Подписка подтверждена. Когда новый план появится в "
        "полигоне Гинот hа-Ир (сейчас отслеживается {count}), вы получите одно "
        "письмо в день; планы, вынесенные на возражения, выделены.",
        "all_digest_subject": "Новые планы в Гинот hа-Ир",
        "all_digest_intro": "В полигон Гинот hа-Ир добавлено новых планов: {count}:",
        "all_deposited_header": "Вынесены на возражения:",
        "all_new_header": "Другие новые планы:",
        "all_item": "{number} - {name}",
        "all_item_status": "Статус: {status}",
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
        "all_confirm_subject": "በጊኖት ሃዒር ስለ አዳዲስ ዕቅዶች ዝመናዎች ምዝገባ አረጋግጥ",
        "all_confirm_intro": "በጊኖት ሃዒር ፖሊጎን ውስጥ ስለ እያንዳንዱ አዲስ ዕቅድ ዝመናዎችን "
        "ለማረጋገጥ ይህን ይክፈቱ: {url}",
        "all_welcome_subject": "ለጊኖት ሃዒር አዳዲስ ዕቅዶች ዝመናዎች ተመዝግበዋል",
        "all_welcome_intro": "ምዝገባው ተረጋግጧል። አዲስ ዕቅድ ወደ ጊኖት ሃዒር ፖሊጎን ሲገባ "
        "(አሁን {count} ዕቅዶች በክትትል ላይ ናቹ) አንድ የዕለት ዝመና ይደርስዎታል፤ ለተቃውሞ "
        "የተቀረጹ ዕቅዶች ይጎለበታሉ።",
        "all_digest_subject": "አዳዲስ ዕቅዶች በጊኖት ሃዒር",
        "all_digest_intro": "{count} አዳዲስ ዕቅዶች ወደ ጊኖት ሃዒር ፖሊጎን ገብተዋል:",
        "all_deposited_header": "ለተቃውሞ የተቀረጹ:",
        "all_new_header": "ሌሎች አዳዲስ ዕቅዶች:",
        "all_item": "{number} - {name}",
        "all_item_status": "ሁኔታ: {status}",
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
        "all_confirm_subject": "Confirmer l'abonnement aux nouveaux plans de Ginot HaIr",
        "all_confirm_intro": "Pour confirmer les mises à jour sur chaque nouveau "
        "plan du polygone Ginot HaIr, ouvrez : {url}",
        "all_welcome_subject": "Abonnement aux nouveaux plans de Ginot HaIr confirmé",
        "all_welcome_intro": "Abonnement confirmé. Quand un nouveau plan entre dans "
        "le polygone Ginot HaIr ({count} plans suivis actuellement), vous recevrez "
        "une mise à jour quotidienne ; les plans déposés pour opposition sont mis "
        "en évidence.",
        "all_digest_subject": "Nouveaux plans à Ginot HaIr",
        "all_digest_intro": "{count} nouveaux plans sont entrés dans le polygone "
        "Ginot HaIr :",
        "all_deposited_header": "Déposés pour opposition :",
        "all_new_header": "Autres nouveaux plans :",
        "all_item": "{number} - {name}",
        "all_item_status": "Statut : {status}",
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
    return (
        plan.get("objection_deadline_derived_2m_from_publication")
        or plan.get("objection_deadline_derived_60d_from_publication")
        or plan.get("objection_deadline")
        or ""
    )


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
    ok = _kv(
        "set", f"pending:{token}", json.dumps(record), "EX", str(PENDING_TTL_SECONDS)
    )
    return ok == "OK"


def confirm_pending(token: str) -> dict | None:
    """Atomically consume a pending record (GETDEL: two interleaved confirms
    cannot both succeed). Creates the subscription when it asked for one."""
    raw = _kv("getdel", f"pending:{token}")
    if not raw:
        return None
    record = json.loads(raw)
    if record.get("subscribe"):
        unsub = secrets.token_urlsafe(24)
        sub = dict(
            record,
            unsub_token=unsub,
            confirmed_at=int(time.time()),
            deadline_notified="",
        )
        if _kv("set", f"sub:{unsub}", json.dumps(sub)) != "OK":
            return None
        _kv("sadd", f"plans:{record['plan']}", unsub)
        _kv("sadd", "plans", record["plan"])
        record["unsub_token"] = unsub
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


def _unsub_url(token: str) -> str:
    return f"{BASE_URL}/api/send_plan_email?action=unsubscribe&token={token}"


def _one_click(msg: MIMEText, unsub_token: str) -> None:
    """RFC 8058 one-click unsubscribe headers (POST to the unsubscribe URL)."""
    if unsub_token:
        msg["List-Unsubscribe"] = f"<{_unsub_url(unsub_token)}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"


def compose(
    plan: dict, to_addr: str, lang: str = "he", unsub_token: str = ""
) -> MIMEText:
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
        url = _unsub_url(unsub_token)
        lines += ["", s["unsub"].format(url=url)]
    msg = _message(s["subject"].format(number=number), lines, to_addr)
    _one_click(msg, unsub_token)
    return msg


def compose_confirm(record: dict, token: str) -> MIMEText:
    """Double opt-in: the confirmation email in the subscriber's language."""
    s = _strings(record.get("lang", "he"))
    url = f"{BASE_URL}/api/send_plan_email?action=confirm&token={token}"
    if record["plan"] == ALL_SCOPE:
        subject = s["all_confirm_subject"]
        intro = s["all_confirm_intro"].format(url=url)
    else:
        subject = s["confirm_subject"].format(number=record["plan"])
        intro = s["confirm_intro"].format(number=record["plan"], url=url)
    lines = [intro, "", s["confirm_expiry"]]
    return _message(subject, lines, record["email"])


def compose_all_welcome(record: dict, plan_count: int) -> MIMEText:
    """The all-scope welcome mail (sent at confirm instead of a plan email:
    the subscription covers every plan in the polygon)."""
    s = _strings(record.get("lang", "he"))
    lines = [
        s["all_welcome_intro"].format(count=plan_count),
        "",
        s["disclaimer"],
        "",
        s["unsub"].format(url=_unsub_url(record["unsub_token"])),
    ]
    msg = _message(s["all_welcome_subject"], lines, record["email"])
    _one_click(msg, record["unsub_token"])
    return msg


def _plan_lines(plan: dict, s: dict) -> list[str]:
    """One digest item: number - name, then status/deadline/mavat when known."""
    lines = [
        s["all_item"].format(
            number=plan.get("pl_number", ""), name=plan.get("pl_name") or ""
        )
    ]
    status = plan_status(plan)
    if status:
        lines.append(s["all_item_status"].format(status=status))
    deadline = plan_deadline(plan)
    if deadline:
        lines.append(s["deadline"].format(deadline=deadline))
    mavat = plan.get("mavat_url") or ""
    if mavat:
        lines.append(s["mavat"].format(url=mavat))
    return lines


def compose_all_digest(record: dict, deposited: list, other: list) -> MIMEText:
    """The daily new-plans digest for all-scope subscribers; plans deposited
    for objections come first, highlighted under their own header."""
    s = _strings(record.get("lang", "he"))
    lines = [s["all_digest_intro"].format(count=len(deposited) + len(other)), ""]
    if deposited:
        lines.append(s["all_deposited_header"])
        for plan in deposited:
            lines += _plan_lines(plan, s) + [""]
    if other:
        lines.append(s["all_new_header"])
        for plan in other:
            lines += _plan_lines(plan, s) + [""]
    lines += [
        s["disclaimer"],
        "",
        s["unsub"].format(url=_unsub_url(record["unsub_token"])),
    ]
    msg = _message(s["all_digest_subject"], lines, record["email"])
    _one_click(msg, record["unsub_token"])
    return msg


def compose_notify(record: dict, reason: str) -> MIMEText:
    """The subscription notification (status change / deadline near)."""
    s = _strings(record.get("lang", "he"))
    plan = record["plan"]
    lines = [reason, "", s["unsub"].format(url=_unsub_url(record["unsub_token"]))]
    msg = _message(s["subject"].format(number=plan), lines, record["email"])
    _one_click(msg, record["unsub_token"])
    return msg


def _log_failure(where: str, exc: Exception) -> None:
    """Operator log line: the stage and the exception class only. Never the
    message, the address or any credential (SMTP errors can echo them)."""
    code = getattr(exc, "smtp_code", "")
    print(f"send_plan_email failure stage={where} error={type(exc).__name__} {code}")


def _is_daily_quota_refusal(exc: smtplib.SMTPRecipientsRefused) -> bool:
    """Gmail's daily sending limit (550 5.4.5) arrives as a per-recipient
    RCPT refusal, but it is account-wide: every remaining recipient would
    fail the same way, and each attempt costs a fresh SMTP login (#1007).
    """
    return any(b"5.4.5" in bytes(resp) for _code, resp in exc.recipients.values())


def _mark_delivered(record: dict) -> None:
    record["all_pending"] = []  # delivered: clear only now
    save_subscription(record["unsub_token"], record)


def _deliver(build, args: tuple, to_addr: str, stage: str, on_sent) -> str:
    """One send inside the notify/digest loops; returns "sent", "failed"
    (skip to the next recipient) or "stop" (abort the run with a 502).
    Compose/save errors are record-specific (#1007): one malformed stored
    record must not 502 the run and starve everyone after it (#997).
    Recipient refusals stay per-recipient, except a daily-quota refusal
    (550 5.4.5), which is account-wide and stops the run."""
    try:
        msg = build(*args)
    except Exception as exc:  # noqa: BLE001 - record-specific (#1007)
        _log_failure(stage + "-compose", exc)
        return "failed"
    try:
        send(msg, to_addr)
    except smtplib.SMTPRecipientsRefused as exc:
        _log_failure(stage, exc)
        return "stop" if _is_daily_quota_refusal(exc) else "failed"
    except Exception as exc:  # noqa: BLE001 - account/transport-wide
        _log_failure(stage, exc)
        return "stop"
    try:
        on_sent()
    except Exception as exc:  # noqa: BLE001 - record-specific (#1007)
        _log_failure(stage + "-save", exc)
    return "sent"


def send(msg: MIMEText, to_addr: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    if port == 587:  # submission port: STARTTLS instead of implicit SSL
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg, from_addr=user, to_addrs=[to_addr])
        return
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg, from_addr=user, to_addrs=[to_addr])


def _valid_email(addr: str) -> bool:
    if not addr or len(addr) > 254 or addr.count("@") != 1:
        return False
    if any(c in addr for c in ",;<>") or any(
        ord(c) <= 32 or ord(c) == 127 for c in addr
    ):
        return False
    local, _, domain = addr.rpartition("@")
    return bool(local) and "." in domain and not domain.startswith((".", "-"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _incr(key: str, ttl: int) -> int:
    """Atomic counter in KV (INCR, EXPIRE on first hit); in-memory fallback
    when KV answers nothing."""
    n = _kv("incr", key)
    if n is None:
        _DAILY[key] = _DAILY.get(key, 0) + 1
        return _DAILY[key]
    if int(n) == 1:
        _kv("expire", key, str(ttl))
    return int(n)


def _over_limit(ip: str, email: str = "", per_ip: bool = True) -> bool:
    """Count one message against the caps; True when any cap is exceeded."""
    now = time.gmtime()
    hour, day = time.strftime("%Y%m%d%H", now), time.strftime("%Y%m%d", now)
    over = _incr(f"rl:day:{day}", 172800) > DAILY_SEND_CAP
    if per_ip:
        over |= _incr(f"rl:ip:{_digest(ip)}:{hour}", 7200) > PER_IP_HOURLY_CAP
    if email:
        key = f"rl:to:{_digest(email.lower())}:{day}"
        over |= _incr(key, 172800) > PER_RECIPIENT_DAILY_CAP
    return over


def _subscription_notices(plans: dict) -> list[tuple[dict, str]]:
    """(record, reason) for subscribers due a notification: one on every
    status change, and one per deadline once it is within the window."""
    out = []
    for token, record in iter_subscriptions():
        plan = plans.get(record.get("plan", ""))
        if not plan:
            continue
        record["unsub_token"] = token
        status = plan_status(plan)
        deadline = plan_deadline(plan)
        s = _strings(record.get("lang", "he"))
        if status and status != record.get("status"):
            reason = s["notify_status"].format(number=record["plan"], status=status)
        elif (
            deadline
            and 0 <= _days_until(deadline) <= NOTIFY_WINDOW_DAYS
            and record.get("deadline_notified") != deadline
        ):
            reason = s["notify_deadline"].format(
                number=record["plan"], deadline=deadline
            )
            record["deadline_notified"] = deadline
        else:
            continue
        record["status"] = status
        out.append((record, reason))
    return out


def _all_scope_notices(plans: dict) -> list[tuple[dict, tuple[list, list]]]:
    """(record, (deposited, other)) for all-scope subscribers when new plans
    appeared in the dataset since the last cron run. The known-plan set is
    global (not per subscriber): the first ever run seeds it silently so
    nobody receives the backlog, and a subscriber who joins later is only
    told about plans arriving after that. Each subscriber's undelivered
    plans are persisted in the record's all_pending BEFORE the digest is
    sent (cleared only after a successful send), so a capped or failed
    cron run never loses a digest."""
    raw = _kv("get", KNOWN_PLANS_KEY)
    if raw is None:  # first run: seed without notifying
        _kv("set", KNOWN_PLANS_KEY, json.dumps(sorted(plans)))
        return []
    known = set(json.loads(raw))
    new_numbers = [number for number in plans if number not in known]
    if new_numbers:
        # Union, not replace: a partial publish must not resurrect dropped
        # plans as a later "new" backlog.
        _kv("set", KNOWN_PLANS_KEY, json.dumps(sorted(known | set(plans))))
    out = []
    for token in _kv("smembers", f"plans:{ALL_SCOPE}") or []:
        sub_raw = _kv("get", f"sub:{token}")
        if not sub_raw:
            continue
        record = json.loads(sub_raw)
        pending = list(dict.fromkeys(record.get("all_pending", []) + new_numbers))
        pending = [number for number in pending if number in plans]
        if pending != record.get("all_pending", []):
            record["all_pending"] = pending
            save_subscription(token, record)
        if not pending:
            continue
        record["unsub_token"] = token
        due = [plans[number] for number in pending]
        deposited = [plan for plan in due if plan.get("_open_obj")]
        other = [plan for plan in due if not plan.get("_open_obj")]
        out.append((record, (deposited, other)))
    return out


def _days_until(iso_date: str) -> int:
    """Whole days from today (UTC) to the YYYY-MM-DD date; -1 when unparseable."""
    import datetime

    try:
        then = datetime.date.fromisoformat(iso_date[:10])
    except ValueError:
        return -1
    return (then - datetime.datetime.now(datetime.timezone.utc).date()).days


def _action_page(text: str, button: str = "", action_url: str = "") -> str:
    form = ""
    if button:
        form = (
            f'<form method="post" action="{html.escape(action_url)}">'
            f'<button type="submit">{html.escape(button)}</button></form>'
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex"></head><body>'
        f"<p>{html.escape(text)}</p>{form}</body></html>"
    )


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: bytes, ctype: str, cors: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if cors:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _reply(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self._send(code, payload, "application/json; charset=utf-8", cors=True)

    def _reply_html(
        self, code: int, text: str, button: str = "", url: str = ""
    ) -> None:
        payload = _action_page(text, button, url).encode("utf-8")
        self._send(code, payload, "text/html; charset=utf-8")

    def _query(self) -> dict:
        from urllib.parse import parse_qs, urlparse

        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _client_ip(self) -> str:
        """The platform-set client address (not the client-appendable
        x-forwarded-for chain) when present."""
        for name in ("x-vercel-forwarded-for", "x-real-ip", "x-forwarded-for"):
            value = self.headers.get(name)
            if value:
                return value.split(",")[0].strip()
        return self.client_address[0]

    def do_OPTIONS(self) -> None:  # CORS preflight: no body
        self._send(204, b"", "text/plain", cors=True)

    def do_GET(self) -> None:
        q = self._query()
        action = q.get("action", "")
        token = urllib.parse.quote(q.get("token", ""), safe="")
        # Confirm/unsubscribe GETs only show a button; the state change is the
        # button's POST, so mail link scanners and prefetchers change nothing.
        if action == "confirm":
            return self._reply_html(
                200,
                "Press to confirm and receive the plan email / לחצו לאישור וקבלת המייל",
                "Confirm / אישור",
                f"?action=confirm&token={token}",
            )
        if action == "unsubscribe":
            return self._reply_html(
                200,
                "Press to unsubscribe / לחצו להסרה מרשימת העדכונים",
                "Unsubscribe / הסרה",
                f"?action=unsubscribe&token={token}",
            )
        if action == "notify":
            secret = os.environ.get("CRON_SECRET", "")
            auth = self.headers.get("Authorization", "")
            if not secret or not hmac.compare_digest(auth, f"Bearer {secret}"):
                return self._reply(403, {"ok": False})
            try:
                plans = load_plans()
                notices = _subscription_notices(plans)
                digests = _all_scope_notices(plans)
            except Exception:  # noqa: BLE001 - generic 502, never leak internals
                return self._reply(502, {"ok": False})
            # #997: each send gets its own try - one permanently failing
            # recipient must not 502 the run and starve everyone after
            # them in smembers order. Failed sends keep their state
            # (un-cleared all_pending / un-saved notice), so the next
            # cron run retries them; the operator log line names the
            # stage and exception class only. Only recipient-specific
            # failures (SMTPRecipientsRefused: a refused RCPT) continue
            # to the next subscriber. An account- or transport-wide
            # error (auth, missing config, connect failure) would fail
            # every send alike, so stop the run with a 502 there instead
            # of burning one fresh SMTP login per remaining recipient -
            # repeated failed logins from one IP can lock the account
            # (#1003 review P2).
            outcomes = []
            for record, reason in notices:
                if _over_limit("", per_ip=False):
                    break
                outcomes.append(
                    _deliver(
                        compose_notify,
                        (record, reason),
                        record["email"],
                        "notify",
                        functools.partial(
                            save_subscription, record["unsub_token"], record
                        ),
                    )
                )
                if outcomes[-1] == "stop":
                    return self._reply(502, {"ok": False})
            for record, (deposited, other) in digests:
                if _over_limit("", per_ip=False):
                    break
                outcomes.append(
                    _deliver(
                        compose_all_digest,
                        (record, deposited, other),
                        record["email"],
                        "all-digest",
                        functools.partial(_mark_delivered, record),
                    )
                )
                if outcomes[-1] == "stop":
                    return self._reply(502, {"ok": False})
            sent = outcomes.count("sent")
            failed = outcomes.count("failed")
            return self._reply(200, {"ok": True, "sent": sent, "failed": failed})
        return self._reply(404, {"ok": False})

    def _confirm(self, token: str) -> None:
        """POST ?action=confirm: consume the pending record, send the plan
        email (and create the subscription when it asked for one)."""
        if _over_limit(self._client_ip(), per_ip=False):
            return self._reply_html(429, "Try again later / נסו שוב מאוחר יותר")
        record = confirm_pending(token)
        if not record:
            return self._reply_html(400, "Invalid or expired link / הקישור אינו תקף")
        try:
            if record["plan"] == ALL_SCOPE:
                send(
                    compose_all_welcome(record, len(load_plans())),
                    record["email"],
                )
            else:
                plan = load_plans().get(record["plan"])
                if not plan:
                    raise LookupError
                send(
                    compose(
                        plan,
                        record["email"],
                        record.get("lang", "he"),
                        record.get("unsub_token", ""),
                    ),
                    record["email"],
                )
        except Exception:  # noqa: BLE001 - generic 502, never leak internals
            if record.get("unsub_token"):
                unsubscribe(record["unsub_token"])
            store_pending(
                token, {k: v for k, v in record.items() if k != "unsub_token"}
            )
            return self._reply_html(502, "Try again later / נסו שוב מאוחר יותר")
        return self._reply_html(200, "Done - the email is on its way / המייל בדרך")

    def do_POST(self) -> None:
        q = self._query()
        action = q.get("action", "")
        if action == "confirm":
            return self._confirm(q.get("token", ""))
        if action == "unsubscribe":
            ok = unsubscribe(q.get("token", ""))
            return self._reply_html(
                200 if ok else 400,
                "Unsubscribed / הוסרתם מהרשימה"
                if ok
                else "Invalid link / קישור לא תקף",
            )
        # Generic responses only: no oracle on plan existence or send state.
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 4096:
                return self._reply(400, {"ok": False})
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._reply(400, {"ok": False})
        if not isinstance(body, dict):
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
        if str(body.get("scope", "")).strip() == "all":
            # Whole-polygon subscription: no plan lookup, always subscribed.
            plan_number = ALL_SCOPE
            subscribe = True
        if not _valid_email(email) or not plan_number:
            return self._reply(400, {"ok": False})
        if not (KV_URL and KV_TOKEN):  # no storage: never send unconfirmed mail
            return self._reply(503, {"ok": False})

        if _over_limit(self._client_ip(), email):
            return self._reply(429, {"ok": False})

        if plan_number == ALL_SCOPE:
            plan = {}
        else:
            try:
                plan = load_plans().get(plan_number)
            except Exception:  # noqa: BLE001 - generic 502, never leak internals
                return self._reply(502, {"ok": False})
            if not plan:
                return self._reply(400, {"ok": False})

        token = secrets.token_urlsafe(24)
        record = {
            "email": email,
            "plan": plan_number,
            "lang": lang,
            "subscribe": subscribe,
            "created": int(time.time()),
            "status": plan_status(plan),
        }
        try:
            if not store_pending(token, record):
                return self._reply(502, {"ok": False})
            send(compose_confirm(record, token), email)
        except Exception as exc:  # noqa: BLE001 - generic 502, never leak internals
            _log_failure("confirm-send", exc)
            return self._reply(502, {"ok": False})
        return self._reply(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:  # no request logging
        pass
