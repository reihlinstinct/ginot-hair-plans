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


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Fresh throttle/cache state and sender env per test."""
    spe._IP_HITS.clear()
    spe._DAILY.clear()
    spe._CACHE.update(at=0.0, plans={})
    for var in ("EMAIL_FROM_NAME", "EMAIL_REPLY_TO", "EMAIL_FROM_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")


def _post(payload: dict, ip: str = "203.0.113.1"):
    """Run do_POST on a socket-free handler; return (status, json body)."""
    h = spe.handler.__new__(spe.handler)
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


def test_happy_path_sends(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    code, body = _post({"email": "v@example.com", "plan_number": PLAN["pl_number"]})
    assert code == 200 and body == {"ok": True}
    assert [to for _, to in sent] == ["v@example.com"]


# Section: throttles


def test_per_ip_hourly_cap(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    payload = {"email": "v@example.com", "plan_number": PLAN["pl_number"]}
    for _ in range(spe.PER_IP_HOURLY_CAP):
        assert _post(payload)[0] == 200
    assert _post(payload)[0] == 429
    assert _post(payload, ip="198.51.100.9")[0] == 200  # another IP unaffected
    assert len(sent) == spe.PER_IP_HOURLY_CAP + 1


def test_daily_cap(monkeypatch):
    _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    today = time.strftime("%Y-%m-%d", time.gmtime())
    spe._DAILY[today] = spe.DAILY_SEND_CAP
    code, _ = _post(
        {"email": "v@example.com", "plan_number": PLAN["pl_number"]},
        ip="192.0.2.7",
    )
    assert code == 429


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


# Section: subscription flow (storage faked)


def test_subscribe_sends_confirmation(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    stored = {}
    monkeypatch.setattr(
        spe,
        "store_pending",
        lambda token, record: stored.update({token: record}) or True,
    )
    code, _ = _post(
        {
            "email": "v@example.com",
            "plan_number": PLAN["pl_number"],
            "lang": "en",
            "subscribe": True,
        }
    )
    assert code == 200
    assert len(sent) == 2  # plan email + confirmation email
    record = next(iter(stored.values()))
    assert record["lang"] == "en" and record["plan"] == PLAN["pl_number"]
    confirm = sent[1][0].get_payload(decode=True).decode("utf-8")
    assert "action=confirm&token=" in confirm


def test_subscribe_without_storage_still_sends(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    monkeypatch.setattr(spe, "store_pending", lambda token, record: False)
    code, _ = _post(
        {"email": "v@example.com", "plan_number": PLAN["pl_number"], "subscribe": True}
    )
    assert code == 200
    assert len(sent) == 1  # one-time email only, no confirmation


def test_confirm_and_unsubscribe(monkeypatch):
    monkeypatch.setattr(
        spe, "confirm_pending", lambda token: {"plan": "x"} if token == "good" else None
    )
    assert _get("/api/send_plan_email?action=confirm&token=good")[0] == 200
    assert _get("/api/send_plan_email?action=confirm&token=bad")[0] == 400
    monkeypatch.setattr(spe, "unsubscribe", lambda token: token == "good")
    assert _get("/api/send_plan_email?action=unsubscribe&token=good")[0] == 200
    assert _get("/api/send_plan_email?action=unsubscribe&token=bad")[0] == 400


def test_notify_requires_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert _get("/api/send_plan_email?action=notify")[0] == 403
    code, _ = _get(
        "/api/send_plan_email?action=notify",
        {"Authorization": "Bearer wrong"},
    )
    assert code == 403


def test_notify_sends_due_notices(monkeypatch):
    sent = _fake_send(monkeypatch)
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    monkeypatch.setattr(spe, "load_plans", lambda: {PLAN["pl_number"]: PLAN})
    record = {
        "email": "v@example.com",
        "plan": PLAN["pl_number"],
        "lang": "he",
        "unsub_token": "tok",
    }
    monkeypatch.setattr(
        spe, "_subscription_notices", lambda plans: [(record, "deadline near")]
    )
    saved = {}
    monkeypatch.setattr(spe, "save_subscription", lambda t, r: saved.update({t: r}))
    code, body = _get(
        "/api/send_plan_email?action=notify", {"Authorization": "Bearer s3cret"}
    )
    assert code == 200 and b'"sent": 1' in body.encode() or b'"sent":1' in body.encode()
    assert sent and "tok" in str(saved)


def test_days_until():
    assert spe._days_until("not-a-date") == -1
    assert spe._days_until("2999-01-01") > 0


def test_kv_inert_without_config(monkeypatch):
    monkeypatch.setattr(spe, "KV_URL", "")
    monkeypatch.setattr(spe, "KV_TOKEN", "")
    assert spe._kv("get", "anything") is None
    assert spe.store_pending("t", {}) is False
    assert list(spe.iter_subscriptions()) == []
