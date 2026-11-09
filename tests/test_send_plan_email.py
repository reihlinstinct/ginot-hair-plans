"""Tests for the on-demand plan email endpoint (api/send_plan_email.py).

No network and no credentials: SMTP and the public-data fetch are faked.
The api/ directory is not a package, so the module is imported by path.
"""

import importlib.util
import io
import json
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "send_plan_email", ROOT / "api" / "send_plan_email.py"
)
spe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spe)

PLAN = {
    "pl_number": "101-0999999",
    "pl_name": "תכנית בדיקה",
    "land_status": "הפקדה",
    "objection_deadline_derived_60d_from_publication": "2026-12-01",
    "mavat_url": "https://mavat.iplan.gov.il/SV4/1/99009999999/310",
}


class FakeKV:
    """In-memory stand-in for the Upstash REST commands the function uses."""

    def __init__(self):
        self.d = {}

    def __call__(self, *a):
        cmd, args = a[0], a[1:]
        if cmd == "set":
            self.d[args[0]] = args[1]
            return "OK"
        if cmd == "get":
            return self.d.get(args[0])
        if cmd == "getdel":
            return self.d.pop(args[0], None)
        if cmd == "del":
            return 1 if self.d.pop(args[0], None) is not None else 0
        if cmd == "incr":
            self.d[args[0]] = int(self.d.get(args[0], 0)) + 1
            return self.d[args[0]]
        if cmd == "expire":
            return 1
        if cmd == "sadd":
            self.d.setdefault(args[0], set()).add(args[1])
            return 1
        if cmd == "srem":
            self.d.get(args[0], set()).discard(args[1])
            return 1
        if cmd == "smembers":
            return sorted(self.d.get(args[0], set()))
        raise AssertionError(cmd)

    def pending(self):
        return {k: v for k, v in self.d.items() if k.startswith("pending:")}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Fresh throttle/cache state and sender env per test."""
    spe._DAILY.clear()
    spe._CACHE.update(at=0.0, plans={})
    for var in ("EMAIL_FROM_NAME", "EMAIL_REPLY_TO", "EMAIL_FROM_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(spe, "KV_URL", "https://kv.example")
    monkeypatch.setattr(spe, "KV_TOKEN", "tok")
    monkeypatch.setattr(spe, "_kv", FakeKV())


def _post(payload: dict, ip: str = "203.0.113.1"):
    """Run do_POST on a socket-free handler; return (status, json body)."""
    h = spe.handler.__new__(spe.handler)
    h.path = "/api/send_plan_email"
    raw = json.dumps(payload).encode("utf-8")
    h.rfile = io.BytesIO(raw)
    h.wfile = io.BytesIO()
    h.headers = {"Content-Length": str(len(raw)), "x-forwarded-for": ip}
    h.client_address = (ip, 12345)
    codes = []
    h.send_response = codes.append
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda: None
    h.do_POST()
    return codes[0], json.loads(h.wfile.getvalue().decode("utf-8"))


def _fake_send(monkeypatch):
    sent = []
    monkeypatch.setattr(spe, "send", lambda msg, to_addr: sent.append((msg, to_addr)))
    return sent


# Section: email composition


def test_compose_identity_and_content():
    msg = spe.compose(PLAN, "visitor@example.com")
    assert msg["To"] == "visitor@example.com"
    assert "reihlinstinct" in str(msg["From"])
    assert msg["Reply-To"] == "reihlinstinct@gmail.com"
    assert PLAN["pl_number"] in str(msg["Subject"])
    body = msg.get_payload(decode=True).decode("utf-8")
    assert "2026-12-01" in body  # deadline fallback field
    assert PLAN["mavat_url"] in body
    assert body.rstrip().endswith("reihlinstinct")


def test_compose_env_overrides(monkeypatch):
    monkeypatch.setenv("EMAIL_FROM_NAME", "Other Name")
    monkeypatch.setenv("EMAIL_REPLY_TO", "")
    msg = spe.compose(PLAN, "visitor@example.com")
    assert "Other Name" in str(msg["From"])
    assert msg["Reply-To"] is None


def test_compose_2m_deadline_preferred():
    plan = dict(PLAN, objection_deadline_derived_2m_from_publication="2026-11-20")
    body = spe.compose(plan, "v@example.com").get_payload(decode=True).decode("utf-8")
    assert "2026-11-20" in body


# Section: validation and honeypot


def test_invalid_email_rejected(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    code, body = _post({"email": "not-an-email", "plan_number": PLAN["pl_number"]})
    assert code == 400 and body == {"ok": False}
    assert sent == []


def test_honeypot_fakes_success(monkeypatch):
    sent = _fake_send(monkeypatch)
    code, body = _post(
        {"email": "v@example.com", "plan_number": PLAN["pl_number"], "website": "x"}
    )
    assert code == 200 and body == {"ok": True}
    assert sent == []  # nothing sent, no plan lookup needed


def test_unknown_plan_rejected(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", dict)
    code, _ = _post({"email": "v@example.com", "plan_number": "000-0000000"})
    assert code == 400
    assert sent == []


def _plans(monkeypatch):
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})


def test_request_sends_only_confirmation(monkeypatch):
    """Nothing but the confirmation goes out before the owner confirms."""
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    code, body = _post({"email": "v@example.com", "plan_number": PLAN["pl_number"]})
    assert code == 200 and body == {"ok": True}
    assert [to for _, to in sent] == ["v@example.com"]
    text = sent[0][0].get_payload(decode=True).decode("utf-8")
    assert "action=confirm&token=" in text
    assert PLAN["mavat_url"] not in text  # the plan email itself is not sent yet
    assert len(spe._kv.pending()) == 1


def test_no_storage_refuses_and_sends_nothing(monkeypatch):
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    monkeypatch.setattr(spe, "KV_URL", "")
    code, _ = _post({"email": "v@example.com", "plan_number": PLAN["pl_number"]})
    assert code == 503 and sent == []


def test_storage_write_failure_sends_nothing(monkeypatch):
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    monkeypatch.setattr(spe, "store_pending", lambda token, record: False)
    code, _ = _post({"email": "v@example.com", "plan_number": PLAN["pl_number"]})
    assert code == 502 and sent == []


# Section: throttles (counters live in KV)


def test_per_ip_hourly_cap(monkeypatch):
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    for i in range(spe.PER_IP_HOURLY_CAP):
        payload = {"email": f"v{i}@example.com", "plan_number": PLAN["pl_number"]}
        assert _post(payload)[0] == 200
    over = {"email": "x@example.com", "plan_number": PLAN["pl_number"]}
    assert _post(over)[0] == 429
    assert _post(over, ip="198.51.100.9")[0] == 200  # another IP unaffected
    assert len(sent) == spe.PER_IP_HOURLY_CAP + 1


def test_per_recipient_daily_cap_across_ips(monkeypatch):
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    payload = {"email": "victim@example.com", "plan_number": PLAN["pl_number"]}
    codes = [_post(payload, ip=f"198.51.100.{i}")[0] for i in range(1, 6)]
    assert codes[: spe.PER_RECIPIENT_DAILY_CAP] == [200] * spe.PER_RECIPIENT_DAILY_CAP
    assert set(codes[spe.PER_RECIPIENT_DAILY_CAP :]) == {429}
    assert len(sent) == spe.PER_RECIPIENT_DAILY_CAP


def test_daily_cap(monkeypatch):
    _fake_send(monkeypatch)
    _plans(monkeypatch)
    day = time.strftime("%Y%m%d", time.gmtime())
    spe._kv.d[f"rl:day:{day}"] = spe.DAILY_SEND_CAP
    code, _ = _post(
        {"email": "v@example.com", "plan_number": PLAN["pl_number"]}, ip="192.0.2.7"
    )
    assert code == 429


def test_client_ip_prefers_platform_header(monkeypatch):
    h = spe.handler.__new__(spe.handler)
    h.client_address = ("10.0.0.1", 1)
    h.headers = {
        "x-forwarded-for": "1.1.1.1, 2.2.2.2",
        "x-vercel-forwarded-for": "9.9.9.9",
    }
    assert h._client_ip() == "9.9.9.9"
    h.headers = {"x-forwarded-for": "1.1.1.1, 2.2.2.2"}
    assert h._client_ip() == "1.1.1.1"


def test_address_validation_is_strict():
    ok = spe._valid_email
    assert ok("a@example.com")
    for bad in (
        "a@x.org,b@y.org",
        "a@x.org;b@y.org",
        "a b@x.org",
        "a\tb@x.org",
        "a@@x.org",
        "<a@x.org>",
        "a@x",
        "",
    ):
        assert not ok(bad), bad


# Section: data loading and SMTP


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_load_plans_caches(monkeypatch):
    calls = []
    payload = json.dumps({"rows": [PLAN]}).encode("utf-8")
    monkeypatch.setattr(
        spe.urllib.request,
        "urlopen",
        lambda url, timeout: (calls.append(url), _FakeResponse(payload))[1],
    )
    plans = spe.load_plans()
    assert plans[PLAN["pl_number"]]["pl_name"] == PLAN["pl_name"]
    spe.load_plans()
    assert len(calls) == 1  # second call served from the cache


def test_send_uses_smtp_env(monkeypatch):
    recorded = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            recorded["host"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            recorded["login"] = (user, password)

        def send_message(self, msg, from_addr, to_addrs):
            recorded["sent"] = (from_addr, to_addrs)

    monkeypatch.setattr(spe.smtplib, "SMTP_SSL", FakeSMTP)
    spe.send(spe.compose(PLAN, "v@example.com"), "v@example.com")
    assert recorded["host"] == ("smtp.gmail.com", 465)
    assert recorded["login"] == ("sender@example.com", "secret")
    assert recorded["sent"] == ("sender@example.com", ["v@example.com"])


def _get(path: str, headers: dict | None = None):
    """Run do_GET on a socket-free handler; return (status, body text)."""
    h = spe.handler.__new__(spe.handler)
    h.path = path
    h.rfile = io.BytesIO()
    h.wfile = io.BytesIO()
    h.headers = headers or {}
    h.client_address = ("203.0.113.1", 12345)
    codes = []
    h.send_response = codes.append
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda: None
    h.do_GET()
    return codes[0], h.wfile.getvalue().decode("utf-8")


# Section: localization


def test_all_languages_have_all_keys():
    base = set(spe._STRINGS["he"])
    for lang in spe.LANGS:
        assert set(spe._STRINGS[lang]) == base, lang


def test_compose_in_english():
    body = (
        spe.compose(PLAN, "v@example.com", lang="en")
        .get_payload(decode=True)
        .decode("utf-8")
    )
    assert "You asked for an update on plan" in body
    assert body.rstrip().endswith("reihlinstinct")


def test_unknown_lang_falls_back_to_hebrew():
    body = (
        spe.compose(PLAN, "v@example.com", lang="xx")
        .get_payload(decode=True)
        .decode("utf-8")
    )
    assert "ביקשת עדכון" in body


def test_compose_with_unsubscribe_link():
    body = (
        spe.compose(PLAN, "v@example.com", unsub_token="tok123")
        .get_payload(decode=True)
        .decode("utf-8")
    )
    assert "action=unsubscribe&token=tok123" in body


# Section: confirm, subscribe and unsubscribe (real storage code, faked KV)


def _request(monkeypatch, subscribe: bool, lang: str = "en"):
    """Submit the form; return (sent mails, confirm token)."""
    sent = _fake_send(monkeypatch)
    _plans(monkeypatch)
    code, _ = _post(
        {
            "email": "v@example.com",
            "plan_number": PLAN["pl_number"],
            "lang": lang,
            "subscribe": subscribe,
        }
    )
    assert code == 200
    token = next(iter(spe._kv.pending())).split(":", 1)[1]
    return sent, token


def _post_action(path: str, headers: dict | None = None):
    h = spe.handler.__new__(spe.handler)
    h.path = path
    h.rfile = io.BytesIO()
    h.wfile = io.BytesIO()
    h.headers = headers or {}
    h.client_address = ("203.0.113.5", 1)
    codes = []
    h.send_response = codes.append
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda: None
    h.do_POST()
    return codes[0], h.wfile.getvalue().decode("utf-8")


def test_get_confirm_changes_nothing(monkeypatch):
    sent, token = _request(monkeypatch, subscribe=True)
    code, page = _get(f"/api/send_plan_email?action=confirm&token={token}")
    assert code == 200 and "<form" in page and 'method="post"' in page
    assert len(sent) == 1  # still only the confirmation
    assert f"pending:{token}" in spe._kv.d  # not consumed by a GET (scanner safe)
    assert not [k for k in spe._kv.d if k.startswith("sub:")]


def test_confirm_post_sends_plan_email_once(monkeypatch):
    sent, token = _request(monkeypatch, subscribe=False, lang="en")
    code, _ = _post_action(f"/api/send_plan_email?action=confirm&token={token}")
    assert code == 200 and len(sent) == 2
    body = sent[1][0].get_payload(decode=True).decode("utf-8")
    assert PLAN["mavat_url"] in body and "Objection deadline" in body
    assert not [k for k in spe._kv.d if k.startswith("sub:")]  # one-time only
    assert _post_action(f"/api/send_plan_email?action=confirm&token={token}")[0] == 400
    assert len(sent) == 2  # a second confirm sends nothing


def test_confirm_with_subscribe_creates_one_subscription(monkeypatch):
    sent, token = _request(monkeypatch, subscribe=True)
    assert _post_action(f"/api/send_plan_email?action=confirm&token={token}")[0] == 200
    subs = [k for k in spe._kv.d if k.startswith("sub:")]
    assert len(subs) == 1
    mail = sent[1][0]
    assert "List-Unsubscribe=One-Click" in mail["List-Unsubscribe-Post"]
    unsub = subs[0].split(":", 1)[1]
    assert unsub in mail["List-Unsubscribe"]
    # A second (concurrent) confirm cannot create another subscription.
    assert _post_action(f"/api/send_plan_email?action=confirm&token={token}")[0] == 400
    assert len([k for k in spe._kv.d if k.startswith("sub:")]) == 1


def test_confirm_send_failure_rolls_back(monkeypatch):
    _sent, token = _request(monkeypatch, subscribe=True)

    def boom(msg, to_addr):
        raise OSError("smtp down")

    monkeypatch.setattr(spe, "send", boom)
    assert _post_action(f"/api/send_plan_email?action=confirm&token={token}")[0] == 502
    assert not [k for k in spe._kv.d if k.startswith("sub:")]
    assert f"pending:{token}" in spe._kv.d  # retry possible


def test_unsubscribe_get_is_inert_post_deletes(monkeypatch):
    _sent, token = _request(monkeypatch, subscribe=True)
    _post_action(f"/api/send_plan_email?action=confirm&token={token}")
    unsub = next(k for k in spe._kv.d if k.startswith("sub:")).split(":", 1)[1]
    path = f"/api/send_plan_email?action=unsubscribe&token={unsub}"
    code, page = _get(path)
    assert code == 200 and "<form" in page
    assert f"sub:{unsub}" in spe._kv.d  # GET did not delete
    assert _post_action(path)[0] == 200
    assert f"sub:{unsub}" not in spe._kv.d
    assert _post_action(path)[0] == 400
    assert list(spe.iter_subscriptions()) == []


def test_notify_requires_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert _get("/api/send_plan_email?action=notify")[0] == 403
    code, _ = _get(
        "/api/send_plan_email?action=notify", {"Authorization": "Bearer wrong"}
    )
    assert code == 403


def _subscribe_and_confirm(monkeypatch):
    sent, token = _request(monkeypatch, subscribe=True, lang="en")
    _post_action(f"/api/send_plan_email?action=confirm&token={token}")
    return sent


def test_notify_deadline_notice_is_sent_once(monkeypatch):
    sent = _subscribe_and_confirm(monkeypatch)
    plan = dict(
        PLAN,
        objection_deadline_derived_2m_from_publication=time.strftime(
            "%Y-%m-%d", time.gmtime(time.time() + 3 * 86400)
        ),
    )
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: plan})
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    auth = {"Authorization": "Bearer s3cret"}
    before = len(sent)
    code, body = _get("/api/send_plan_email?action=notify", auth)
    assert code == 200 and '"sent": 1' in body
    assert len(sent) == before + 1
    assert "List-Unsubscribe" in sent[-1][0]
    # Next day's cron: same deadline, same status -> nothing more.
    code, body = _get("/api/send_plan_email?action=notify", auth)
    assert '"sent": 0' in body and len(sent) == before + 1


def test_notify_status_change(monkeypatch):
    sent = _subscribe_and_confirm(monkeypatch)
    changed = dict(PLAN, land_status="אישור")
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: changed})
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    before = len(sent)
    _get("/api/send_plan_email?action=notify", {"Authorization": "Bearer s3cret"})
    assert len(sent) == before + 1


def test_days_until():
    assert spe._days_until("not-a-date") == -1
    assert spe._days_until("2999-01-01") > 0


def test_kv_inert_without_config(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(spe, "KV_URL", "")
    monkeypatch.setattr(spe, "KV_TOKEN", "")
    assert spe._kv("get", "anything") is None
    assert spe.store_pending("t", {}) is False
    assert list(spe.iter_subscriptions()) == []


def test_cors_preflight_has_no_body():
    h = spe.handler.__new__(spe.handler)
    h.wfile = io.BytesIO()
    h.headers = {}
    codes = []
    h.send_response = codes.append
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda: None
    h.do_OPTIONS()
    assert codes == [204] and h.wfile.getvalue() == b""


def test_port_587_uses_starttls(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("init", port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            calls.append("starttls")

        def login(self, user, password):
            calls.append("login")

        def send_message(self, msg, from_addr, to_addrs):
            calls.append("sent")

    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setattr(spe.smtplib, "SMTP", FakeSMTP)
    spe.send(spe.compose(PLAN, "v@example.com"), "v@example.com")
    assert calls == [("init", 587), "starttls", "login", "sent"]


# Section: operator log line for failed sends carries no content
def test_log_failure_names_class_only(capsys):
    exc = RuntimeError("550 rejected user@example.com")
    spe._log_failure("confirm-send", exc)
    out = capsys.readouterr().out
    assert "stage=confirm-send" in out and "RuntimeError" in out
    assert "user@example.com" not in out
