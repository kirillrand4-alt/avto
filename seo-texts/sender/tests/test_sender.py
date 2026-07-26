# FILE: sender/tests/test_sender.py
"""Юнит-тесты sender.Sender.

Сеть SMTP замокана фейковым клиентом; store — реальная временная SQLite-БД,
реализующая подмножество DAL, которым пользуется сендер.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import smtplib  # noqa: E402

from sender.sender import (  # noqa: E402
    Campaign, ConfigError, GateDecision, GateTrippedError, GatesCfg, LegalCfg,
    MailboxCfg, MailboxState, Message, PersonalizationGateError,
    RateLimitExceeded, Recipient, RenderedMessage, SendError, Sender,
    SuppressedError, SuppressionEntry, TransientError, WindowCfg,
)

UTC = timezone.utc
SECRET = "unit-test-secret"


def now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt):
    return None if dt is None else dt.astimezone(UTC).isoformat()


def _dt(s):
    if not s:
        return None
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _b(v):
    return None if v is None else bool(v)


# --------------------------------------------------------------------------- #
# Реальный SQLite-store (подмножество DAL)
# --------------------------------------------------------------------------- #
class SqliteStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init()
        self.events = []

    def _init(self):
        self.conn.executescript(
            """
            CREATE TABLE recipients(
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, domain TEXT,
                inn TEXT, company_name TEXT, okved TEXT, segment TEXT,
                bitrix_id TEXT, contact_name TEXT, mx_provider TEXT,
                valid_status TEXT, catch_all INT, role_based INT, disposable INT,
                source TEXT, extra_json TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE campaigns(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, status TEXT,
                legal_entity TEXT, legal_inn TEXT, provider_pool TEXT,
                config_json TEXT, created_at TEXT, started_at TEXT);
            CREATE TABLE messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT,
                campaign_id INT, recipient_id INT, sequence_step_id INT,
                mailbox_id TEXT, status TEXT, scheduled_at TEXT, claimed_at TEXT,
                sent_at TEXT, rfc_message_id TEXT, in_reply_to TEXT, thread_id TEXT,
                subject TEXT, body_rendered TEXT, unsub_token TEXT,
                attempt_count INT DEFAULT 0, last_error TEXT, retryable INT);
            CREATE TABLE mailbox_state(
                mailbox_id TEXT PRIMARY KEY, provider TEXT, day_key TEXT,
                sent_today INT, sent_total INT, ramp_day INT, daily_limit INT,
                last_sent_at TEXT, paused INT, pause_reason TEXT);
            CREATE TABLE events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, dedup_key TEXT UNIQUE,
                event_type TEXT, event_ts TEXT, message_id INT);
            """
        )
        self.conn.commit()

    # ---- вставка тестовых данных ---- #
    def add_recipient(self, email, domain, provider="yandex", inn=None):
        cur = self.conn.execute(
            "INSERT INTO recipients(email,domain,inn,mx_provider,valid_status,"
            "extra_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (email, domain, inn, provider, "valid", "{}",
             _iso(now_utc()), _iso(now_utc())))
        self.conn.commit()
        return cur.lastrowid

    def add_campaign(self, name="c", pool=None):
        cur = self.conn.execute(
            "INSERT INTO campaigns(name,status,legal_entity,legal_inn,"
            "provider_pool,config_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (name, "active", "ООО Руспром", "7700000000", pool, "{}",
             _iso(now_utc())))
        self.conn.commit()
        return cur.lastrowid

    def add_message(self, campaign_id, recipient_id, *, subject="Тема",
                    body="тело", status="sending", rfc=None, unsub_token=None):
        cur = self.conn.execute(
            "INSERT INTO messages(idempotency_key,campaign_id,recipient_id,"
            "sequence_step_id,status,scheduled_at,subject,body_rendered,"
            "rfc_message_id,unsub_token,attempt_count) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,0)",
            (f"idem-{recipient_id}-{campaign_id}", campaign_id, recipient_id, 1,
             status, _iso(now_utc()), subject, body, rfc, unsub_token))
        self.conn.commit()
        return cur.lastrowid

    def set_mailbox_state(self, mailbox_id, provider, *, day_key, sent_today=0,
                          ramp_day=0, daily_limit=50, last_sent_at=None,
                          paused=False, pause_reason=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO mailbox_state(mailbox_id,provider,day_key,"
            "sent_today,sent_total,ramp_day,daily_limit,last_sent_at,paused,"
            "pause_reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (mailbox_id, provider, day_key, sent_today, sent_today, ramp_day,
             daily_limit, _iso(last_sent_at), int(paused), pause_reason))
        self.conn.commit()

    # ---- методы, вызываемые сендером ---- #
    def get_recipient(self, rid):
        r = self.conn.execute("SELECT * FROM recipients WHERE id=?", (rid,)).fetchone()
        if not r:
            return None
        return Recipient(
            id=r["id"], email=r["email"], domain=r["domain"], inn=r["inn"],
            company_name=r["company_name"], okved=r["okved"], segment=r["segment"],
            bitrix_id=r["bitrix_id"], contact_name=r["contact_name"],
            mx_provider=r["mx_provider"], valid_status=r["valid_status"],
            catch_all=_b(r["catch_all"]), role_based=_b(r["role_based"]),
            disposable=_b(r["disposable"]), source=r["source"],
            extra=json.loads(r["extra_json"] or "{}"),
            created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]))

    def get_campaign(self, cid):
        r = self.conn.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone()
        if not r:
            return None
        return Campaign(
            id=r["id"], name=r["name"], status=r["status"],
            legal_entity=r["legal_entity"], legal_inn=r["legal_inn"],
            provider_pool=r["provider_pool"],
            config=json.loads(r["config_json"] or "{}"),
            created_at=_dt(r["created_at"]), started_at=_dt(r["started_at"]))

    def get_message(self, mid):
        r = self.conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        if not r:
            return None
        return Message(
            id=r["id"], idempotency_key=r["idempotency_key"],
            campaign_id=r["campaign_id"], recipient_id=r["recipient_id"],
            sequence_step_id=r["sequence_step_id"], mailbox_id=r["mailbox_id"],
            status=r["status"], scheduled_at=_dt(r["scheduled_at"]),
            claimed_at=_dt(r["claimed_at"]), sent_at=_dt(r["sent_at"]),
            rfc_message_id=r["rfc_message_id"], in_reply_to=r["in_reply_to"],
            thread_id=r["thread_id"], subject=r["subject"],
            body_rendered=r["body_rendered"], unsub_token=r["unsub_token"],
            attempt_count=r["attempt_count"], last_error=r["last_error"])

    def mark_sent(self, message_id, rfc_message_id, sent_at, *, mailbox_id=None):
        self.conn.execute(
            "UPDATE messages SET status='sent', rfc_message_id=?, sent_at=? "
            "WHERE id=?", (rfc_message_id, _iso(sent_at), message_id))
        self.conn.commit()

    def mark_failed(self, message_id, error, *, retryable):
        self.conn.execute(
            "UPDATE messages SET status='failed', last_error=?, retryable=?, "
            "attempt_count=attempt_count+1 WHERE id=?",
            (error, int(retryable), message_id))
        self.conn.commit()

    def mark_skipped(self, message_id, reason):
        self.conn.execute(
            "UPDATE messages SET status='skipped', last_error=? WHERE id=?",
            (reason, message_id))
        self.conn.commit()

    def increment_sent(self, mailbox_id, *, now):
        day = now.astimezone(UTC).strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT * FROM mailbox_state WHERE mailbox_id=?", (mailbox_id,)
        ).fetchone()
        if row is None:
            self.set_mailbox_state(mailbox_id, "yandex", day_key=day,
                                   sent_today=1, last_sent_at=now)
        else:
            if row["day_key"] != day:
                sent_today, ramp_day = 1, row["ramp_day"] + 1
            else:
                sent_today, ramp_day = row["sent_today"] + 1, row["ramp_day"]
            self.conn.execute(
                "UPDATE mailbox_state SET day_key=?, sent_today=?, "
                "sent_total=sent_total+1, ramp_day=?, last_sent_at=? "
                "WHERE mailbox_id=?",
                (day, sent_today, ramp_day, _iso(now), mailbox_id))
            self.conn.commit()
        return self.get_mailbox_state(mailbox_id)

    def get_mailbox_state(self, mailbox_id):
        r = self.conn.execute(
            "SELECT * FROM mailbox_state WHERE mailbox_id=?", (mailbox_id,)
        ).fetchone()
        if not r:
            return None
        return MailboxState(
            mailbox_id=r["mailbox_id"], provider=r["provider"], day_key=r["day_key"],
            sent_today=r["sent_today"], sent_total=r["sent_total"],
            ramp_day=r["ramp_day"], daily_limit=r["daily_limit"],
            last_sent_at=_dt(r["last_sent_at"]), paused=bool(r["paused"]),
            pause_reason=r["pause_reason"])

    def append_event(self, e):
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO events(dedup_key,event_type,event_ts,message_id) "
            "VALUES(?,?,?,?)",
            (e.dedup_key, e.event_type, _iso(e.event_ts), e.message_id))
        self.conn.commit()
        created = cur.rowcount > 0
        if created:
            self.events.append(e)
        return (cur.lastrowid or 0, created)

    def close(self):
        self.conn.close()


# --------------------------------------------------------------------------- #
# Фейки config / suppression / gates / smtp
# --------------------------------------------------------------------------- #
class FakeConfig:
    def __init__(self, *, tz="UTC", days=(1, 2, 3, 4, 5, 6, 7), start="00:00",
                 end="23:59", holidays=frozenset(), jitter=False):
        self._mailboxes = [
            MailboxCfg("box1@rusprom.ru", "yandex", "smtp.yandex.ru", 465,
                       "imap.yandex.ru", 993, "box1@rusprom.ru", "BOX1_PASSWORD",
                       "Иван Петров, Руспром", None, "pool_yandex"),
            MailboxCfg("box2@rusprom.ru", "yandex", "smtp.yandex.ru", 465,
                       "imap.yandex.ru", 993, "box2@rusprom.ru", "BOX2_PASSWORD",
                       "Пётр Иванов, Руспром", None, "pool_yandex"),
            MailboxCfg("box5@rusprom.ru", "google", "smtp.gmail.com", 465,
                       "imap.gmail.com", 993, "box5@rusprom.ru", "BOX5_PASSWORD",
                       "Иван Петров, Руспром", None, "pool_google", True),
        ]
        self._pools = {
            "pool_yandex": ["box1@rusprom.ru", "box2@rusprom.ru"],
            "pool_google": ["box5@rusprom.ru"],
            "pool_fallback": ["box1@rusprom.ru"],
        }
        self._ramp = {
            "yandex": [50, 50, 50], "google": [2, 3, 5],
        }
        self._window = WindowCfg(tz, tuple(days), start, end)
        self._holidays = set(holidays)
        self._data = {
            "timezone": tz,
            "service.sandbox_smtp": "localhost:8025",
            "service.smtp_timeout_sec": 5,
            "send_pacing.min_interval_sec": 90,
            "send_pacing.max_interval_sec": 420,
            "send_pacing.jitter": jitter,
            "provider_split.match_recipient_provider": True,
            "provider_split.routing": {
                "yandex": "pool_yandex", "google": "pool_google",
                "other": "pool_fallback",
            },
        }

    def mailboxes(self):
        return self._mailboxes

    def provider_pools(self):
        return self._pools

    def ramp_curve(self, provider):
        return self._ramp.get(provider, [])

    def sending_window(self):
        return self._window

    def holidays(self):
        return self._holidays

    def gates(self):
        return GatesCfg(8.0, 0.3, 6.0, 0.1, 50)

    def legal(self):
        return LegalCfg("ООО «Руспром»", "7700000000",
                        "https://parsercompressor.online/u", "UNSUB_SECRET", 24)

    def get(self, key, default=None):
        return self._data.get(key, default)


class FakeSuppression:
    def __init__(self):
        self.suppressed_emails = {}

    def suppress(self, email, reason="manual"):
        self.suppressed_emails[email] = reason

    def is_suppressed(self, recipient):
        reason = self.suppressed_emails.get(recipient.email)
        if reason is None:
            return None
        return SuppressionEntry(1, "email", recipient.email, reason, None, None,
                                now_utc(), None)


class FakeGates:
    def __init__(self):
        self.global_tripped = False
        self.mailbox_tripped = set()
        self.domain_tripped = set()

    def _dec(self, scope, target, tripped):
        return GateDecision(scope, target, tripped, "complaint_pct", 0.0, 0.1,
                            "pause" if tripped else "none")

    def check_global(self):
        return self._dec("global", "*", self.global_tripped)

    def check_mailbox(self, mailbox_id):
        return self._dec("mailbox", mailbox_id, mailbox_id in self.mailbox_tripped)

    def check_domain(self, domain, campaign_id=None):
        return self._dec("domain", domain, domain in self.domain_tripped)


class FakeSMTP:
    """Совместим с smtplib: login/sendmail/quit."""
    instances = []

    def __init__(self, host, port, use_ssl, *, sendmail_exc=None):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.sendmail_exc = sendmail_exc
        self.sent = []
        self.login_args = None
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, from_addr, to_addrs, msg):
        if self.sendmail_exc is not None:
            raise self.sendmail_exc
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        self.quit_called = True


def make_opener(sendmail_exc=None, connect_exc=None):
    def opener(host, port, use_ssl):
        if connect_exc is not None:
            raise connect_exc
        return FakeSMTP(host, port, use_ssl, sendmail_exc=sendmail_exc)
    return opener


# --------------------------------------------------------------------------- #
# Фикстуры
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _secret_env(monkeypatch):
    monkeypatch.setenv("UNSUB_SECRET", SECRET)
    FakeSMTP.instances.clear()


@pytest.fixture
def store(tmp_path):
    s = SqliteStore(tmp_path / "sender.db")
    yield s
    s.close()


@pytest.fixture
def config():
    return FakeConfig()


@pytest.fixture
def parts(store, config):
    supp = FakeSuppression()
    gates = FakeGates()
    return store, config, supp, gates


def build_sender(parts, *, dry_run=True, sendmail_exc=None, connect_exc=None):
    store, config, supp, gates = parts
    sndr = Sender(config, store, supp, gates, dry_run=dry_run)
    sndr._smtp_opener = make_opener(sendmail_exc, connect_exc)
    return sndr


def seed(store, *, provider="yandex", sent_today=0, msg_status="sending",
         mailbox="box1@rusprom.ru", mb_provider="yandex", rfc=None,
         subject="Тема", body="Здравствуйте"):
    day = now_utc().strftime("%Y-%m-%d")
    rid = store.add_recipient("lead@example.ru", "example.ru", provider)
    cid = store.add_campaign()
    mid = store.add_message(cid, rid, status=msg_status, rfc=rfc,
                            subject=subject, body=body)
    store.set_mailbox_state(mailbox, mb_provider, day_key=day,
                            sent_today=sent_today)
    return rid, cid, mid


# --------------------------------------------------------------------------- #
# build_headers
# --------------------------------------------------------------------------- #
def test_build_headers_includes_list_unsubscribe_rfc8058(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    _, cid, mid = seed(store)
    msg = store.get_message(mid)
    camp = store.get_campaign(cid)

    headers = sndr.build_headers(msg, camp, "box1@rusprom.ru")

    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    lu = headers["List-Unsubscribe"]
    # параметр строго `t` — его читает unsub_server._parse_token (фикс П1)
    assert "<https://parsercompressor.online/u?t=" in lu
    assert "<mailto:box1@rusprom.ru?subject=unsubscribe>" in lu
    assert headers["To"] == "lead@example.ru"
    assert "box1@rusprom.ru" in headers["From"]
    assert headers["Message-ID"].startswith("<") and headers["Message-ID"].endswith(">")


def test_build_headers_unknown_mailbox_raises(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    _, cid, mid = seed(store)
    msg = store.get_message(mid)
    with pytest.raises(ConfigError):
        sndr.build_headers(msg, store.get_campaign(cid), "nope@rusprom.ru")


def test_unsub_token_signature_valid(parts):
    """Токен sender'а проверяется ТЕМ ЖЕ ядром, что использует unsub_server
    (sender.tokens) — раньше форматы были несовместимы и ссылка из письма
    не работала (фикс П1, сверх ревью-списка)."""
    sndr = build_sender(parts)
    token = sndr._make_unsub_token(42, 7)
    from sender.tokens import verify_token
    payload = verify_token(SECRET.encode(), token,
                           required_int_fields=("rid", "cid", "ts"))
    assert payload["rid"] == 42
    assert payload["cid"] == 7


def test_build_headers_missing_secret_raises(parts, monkeypatch):
    monkeypatch.delenv("UNSUB_SECRET", raising=False)
    store, *_ = parts
    sndr = build_sender(parts)
    _, cid, mid = seed(store)
    msg = store.get_message(mid)
    with pytest.raises(ConfigError):
        sndr.build_headers(msg, store.get_campaign(cid), "box1@rusprom.ru")


# --------------------------------------------------------------------------- #
# send: happy path + инварианты
# --------------------------------------------------------------------------- #
def test_send_dry_run_happy_path(parts):
    store, *_ = parts
    sndr = build_sender(parts, dry_run=True)
    _, _, mid = seed(store)
    msg = store.get_message(mid)
    rendered = RenderedMessage(subject="Здравствуйте", body="Текст письма")

    result = sndr.send(msg, rendered, "box1@rusprom.ru")

    assert result.ok and result.dry_run
    assert result.rfc_message_id
    persisted = store.get_message(mid)
    assert persisted.status == "sent"
    assert persisted.rfc_message_id == result.rfc_message_id
    # событие sent записано ровно один раз
    assert [e.event_type for e in store.events] == ["sent"]
    assert store.events[0].dedup_key == f"send:{mid}"
    # счётчик ящика увеличился
    assert store.get_mailbox_state("box1@rusprom.ru").sent_today == 1
    # dry-run ушёл в песочницу без логина
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("localhost", 8025)
    assert smtp.login_args is None
    assert len(smtp.sent) == 1


def test_send_unfilled_fields_gate(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    _, _, mid = seed(store)
    msg = store.get_message(mid)
    rendered = RenderedMessage(subject="s", body="b", unfilled_fields=("company_name",))

    with pytest.raises(PersonalizationGateError):
        sndr.send(msg, rendered, "box1@rusprom.ru")

    persisted = store.get_message(mid)
    assert persisted.status == "failed"
    assert persisted.attempt_count == 1
    # retryable=False сохранён
    row = store.conn.execute(
        "SELECT retryable FROM messages WHERE id=?", (mid,)).fetchone()
    assert row["retryable"] == 0
    assert not FakeSMTP.instances  # сеть не трогали


def test_send_suppressed_recipient(parts):
    store, config, supp, gates = parts
    sndr = build_sender(parts)
    _, _, mid = seed(store)
    supp.suppress("lead@example.ru", reason="unsubscribe")
    msg = store.get_message(mid)
    rendered = RenderedMessage(subject="s", body="b")

    with pytest.raises(SuppressedError):
        sndr.send(msg, rendered, "box1@rusprom.ru")

    assert store.get_message(mid).status == "skipped"
    assert not FakeSMTP.instances


def test_send_gate_tripped(parts):
    store, config, supp, gates = parts
    sndr = build_sender(parts)
    _, _, mid = seed(store)
    gates.global_tripped = True
    msg = store.get_message(mid)

    with pytest.raises(GateTrippedError):
        sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")
    assert not FakeSMTP.instances


def test_send_rate_limited_when_daily_limit_reached(parts):
    store, config, *_ = parts
    sndr = build_sender(parts)
    _, _, mid = seed(store, sent_today=50)  # лимит yandex ramp_day0 == 50
    msg = store.get_message(mid)

    with pytest.raises(RateLimitExceeded):
        sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")
    assert not FakeSMTP.instances


def test_send_idempotent_when_already_sent(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    _, _, mid = seed(store, msg_status="sent", rfc="<existing@rusprom.ru>")
    msg = store.get_message(mid)

    result = sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")

    assert result.ok
    assert result.rfc_message_id == "<existing@rusprom.ru>"
    assert not FakeSMTP.instances  # повторной отправки не было


# --------------------------------------------------------------------------- #
# send: классификация SMTP-ошибок
# --------------------------------------------------------------------------- #
def test_send_permanent_error_marks_failed_non_retryable(parts):
    store, *_ = parts
    exc = smtplib.SMTPRecipientsRefused({"lead@example.ru": (550, b"no such user")})
    sndr = build_sender(parts, sendmail_exc=exc)
    _, _, mid = seed(store)
    msg = store.get_message(mid)

    with pytest.raises(SendError):
        sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")

    row = store.conn.execute(
        "SELECT status, retryable FROM messages WHERE id=?", (mid,)).fetchone()
    assert row["status"] == "failed" and row["retryable"] == 0


def test_send_transient_error_marks_failed_retryable(parts):
    store, *_ = parts
    exc = smtplib.SMTPResponseException(451, b"try again later")
    sndr = build_sender(parts, sendmail_exc=exc)
    _, _, mid = seed(store)
    msg = store.get_message(mid)

    with pytest.raises(TransientError):
        sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")

    row = store.conn.execute(
        "SELECT status, retryable FROM messages WHERE id=?", (mid,)).fetchone()
    assert row["status"] == "failed" and row["retryable"] == 1


def test_send_connect_failure_is_transient(parts):
    store, *_ = parts
    sndr = build_sender(parts, connect_exc=ConnectionRefusedError("down"))
    _, _, mid = seed(store)
    msg = store.get_message(mid)
    with pytest.raises(TransientError):
        sndr.send(msg, RenderedMessage("s", "b"), "box1@rusprom.ru")


# --------------------------------------------------------------------------- #
# can_send_now
# --------------------------------------------------------------------------- #
def test_can_send_now_true_default(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    seed(store)
    assert sndr.can_send_now("box1@rusprom.ru", now=now_utc())


def test_can_send_now_false_when_paused(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day, paused=True)
    assert not sndr.can_send_now("box1@rusprom.ru", now=now_utc())


def test_can_send_now_false_outside_window(parts):
    store, config, supp, gates = parts
    cfg = FakeConfig(days=(1, 2, 3, 4, 5), start="09:30", end="18:00")
    sndr = Sender(cfg, store, supp, gates, dry_run=True)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day)
    # суббота 2025-01-04 12:00 UTC — вне рабочих дней
    sat = datetime(2025, 1, 4, 12, 0, tzinfo=UTC)
    assert not sndr.can_send_now("box1@rusprom.ru", now=sat)
    # будний час до окна
    early = datetime(2025, 1, 6, 8, 0, tzinfo=UTC)
    assert not sndr.can_send_now("box1@rusprom.ru", now=early)
    # будний час внутри окна
    ok = datetime(2025, 1, 6, 10, 0, tzinfo=UTC)
    assert sndr.can_send_now("box1@rusprom.ru", now=ok)


def test_can_send_now_pacing_gap(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    recent = now_utc() - timedelta(seconds=10)
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day,
                            last_sent_at=recent)
    assert not sndr.can_send_now("box1@rusprom.ru", now=now_utc())

    old = now_utc() - timedelta(seconds=200)
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day,
                            last_sent_at=old)
    assert sndr.can_send_now("box1@rusprom.ru", now=now_utc())


def test_can_send_now_day_rollover_resets_counter(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    yesterday = (now_utc() - timedelta(days=1)).strftime("%Y-%m-%d")
    # вчера превысили, но с новым днём счётчик обнулён
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=yesterday,
                            sent_today=999, ramp_day=0)
    assert sndr.can_send_now("box1@rusprom.ru", now=now_utc())


# --------------------------------------------------------------------------- #
# pick_mailbox
# --------------------------------------------------------------------------- #
def test_pick_mailbox_routes_by_provider_and_least_loaded(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day, sent_today=3)
    store.set_mailbox_state("box2@rusprom.ru", "yandex", day_key=day, sent_today=1)
    rid = store.add_recipient("y@yandex.ru", "yandex.ru", "yandex")
    cid = store.add_campaign()
    recipient = store.get_recipient(rid)
    campaign = store.get_campaign(cid)

    picked = sndr.pick_mailbox(recipient, campaign)
    assert picked == "box2@rusprom.ru"  # менее загруженный из pool_yandex


def test_pick_mailbox_none_when_all_at_limit(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day, sent_today=50)
    store.set_mailbox_state("box2@rusprom.ru", "yandex", day_key=day, sent_today=50)
    rid = store.add_recipient("y@yandex.ru", "yandex.ru", "yandex")
    cid = store.add_campaign()
    assert sndr.pick_mailbox(store.get_recipient(rid), store.get_campaign(cid)) is None


def test_pick_mailbox_google_pool(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box5@rusprom.ru", "google", day_key=day, sent_today=0)
    rid = store.add_recipient("g@gmail.com", "gmail.com", "google")
    cid = store.add_campaign()
    assert sndr.pick_mailbox(store.get_recipient(rid),
                             store.get_campaign(cid)) == "box5@rusprom.ru"


def test_pick_mailbox_fallback_for_unknown_provider(parts):
    store, *_ = parts
    sndr = build_sender(parts)
    day = now_utc().strftime("%Y-%m-%d")
    store.set_mailbox_state("box1@rusprom.ru", "yandex", day_key=day, sent_today=0)
    rid = store.add_recipient("x@unknown.tld", "unknown.tld", "other")
    cid = store.add_campaign()
    # pool_fallback -> box1
    assert sndr.pick_mailbox(store.get_recipient(rid),
                             store.get_campaign(cid)) == "box1@rusprom.ru"
