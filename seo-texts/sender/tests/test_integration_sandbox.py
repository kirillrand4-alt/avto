# -*- coding: utf-8 -*-
"""Интеграционный прогон на локальной SMTP-песочнице (aiosmtpd).

Сквозной сценарий из SENDER-STATE «ОСТАЁТСЯ» п.3:
волна → bounce → стоп-на-ответ → дедуп → резюм после рестарта.

Реальные модули: Config (боевой YAML из test_config), Store (sqlite),
Suppression, Personalizer, Sender (dry_run → aiosmtpd), Cadence, Gates,
Warmup (выключен конфигом), Analytics, Orchestrator, ImapWatcher.
IMAP-протокол не эмулируем: входящие письма подаются в реальный
ImapWatcher через classify()+_process_event() сырыми RFC822-байтами
(та же обработка, что у poll_once, минус imaplib).
"""

import os
import socket
import sys
import threading
import time as _time
from dataclasses import replace
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

aiosmtpd_controller = pytest.importorskip(
    "aiosmtpd.controller", reason="интеграционной песочнице нужен aiosmtpd"
)
from aiosmtpd.controller import Controller  # noqa: E402

from sender.analytics import Analytics  # noqa: E402
from sender.cadence import Cadence  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.gates import Gates  # noqa: E402
from sender.imap_watcher import ImapWatcher  # noqa: E402
from sender.orchestrator import Orchestrator  # noqa: E402
from sender.personalize import Personalizer  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import (  # noqa: E402
    CampaignIn,
    RecipientIn,
    SequenceStepIn,
    Store,
)
from sender.suppression import Suppression  # noqa: E402
from sender.warmup import Warmup  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


# вторник 12:00 МСК — внутри окна отправки (Mon-Fri 09:30-18:00 Europe/Moscow)
T0 = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
# понедельник 12:00 МСК: > 48ч + 10% джиттера после T0, снова в окне
T1 = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)

ENV = {
    "BOX1_PASSWORD": "p1", "BOX2_PASSWORD": "p2", "BOX3_PASSWORD": "p3",
    "BOX4_PASSWORD": "p4", "BOX5_PASSWORD": "p5",
    "UNSUB_SIGNING_SECRET": "integration-secret-32-bytes!!!!!",
}


@pytest.fixture(scope="module", autouse=True)
def _sandbox_env():
    """Unsub/SMTP-секреты: sender читает их из os.environ, не из Config-env."""
    old = {k: os.environ.get(k) for k in ENV}
    os.environ.update(ENV)
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class CollectingHandler:
    """aiosmtpd-хендлер: копит (mail_from, rcpt_tos, data) потокобезопасно."""

    def __init__(self):
        self.messages = []
        self._lock = threading.Lock()

    async def handle_DATA(self, server, session, envelope):
        with self._lock:
            self.messages.append(
                (envelope.mail_from, list(envelope.rcpt_tos), envelope.content)
            )
        return "250 Message accepted for delivery"

    def to_addrs(self):
        with self._lock:
            return [rcpt for _, rcpts, _ in self.messages for rcpt in rcpts]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def smtp_sandbox():
    """aiosmtpd на свободном порту; живёт на весь модуль."""
    handler = CollectingHandler()
    port = _free_port()
    controller = Controller(handler, hostname="127.0.0.1", port=port)
    controller.start()
    # дать серверу подняться
    for _ in range(50):
        try:
            probe = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            probe.close()
            break
        except OSError:
            _time.sleep(0.05)
    yield handler, port
    controller.stop()


def _make_config(tmp_path, port: int) -> Config:
    yaml_text = (
        BASE_YAML
        .replace('sandbox_smtp: "localhost:8025"', f'sandbox_smtp: "127.0.0.1:{port}"')
        .replace("enabled_providers: [google]", "enabled_providers: []")  # без шума прогрева
        # без межписьменного пейсинга: волна из 3 писем должна уйти одним тиком
        + "\nsend_pacing:\n  min_interval_sec: 0\n"
    )
    p = tmp_path / "config.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return Config.load(p, env=ENV)


def _build_tree(tmp_path, port, db_name="integration.db"):
    """Собирает полное дерево сервиса поверх одной sqlite-базы."""
    config = _make_config(tmp_path, port)
    store = Store(str(tmp_path / db_name))
    store.init_schema()
    suppression = Suppression(store)
    gates = Gates(config, store)
    sender = Sender(config, store, suppression, gates, dry_run=True)
    cadence = Cadence(config, store, suppression)
    warm_leads = []

    class Desk:
        def push_warm_lead(self, recipient, thread_id, snippet):
            warm_leads.append((recipient.email, thread_id, snippet))

    class NoPollImap(ImapWatcher):
        """Реальный ImapWatcher, но poll_once не ходит в сеть: входящие
        подаются тестом через classify()+_process_event() (тот же код-путь)."""

        def poll_once(self, mailbox_id):
            return []

    imap = NoPollImap(config, store, suppression, reply_desk=Desk())
    warmup = Warmup(config, store, sender)
    analytics = Analytics(store)
    personalizer = Personalizer(config)
    orch = Orchestrator(config, store, sender, cadence, gates, imap, warmup,
                        analytics, personalizer=personalizer)
    return orch, store, imap, warm_leads


def _seed_campaign(store, emails):
    cid = store.create_campaign(CampaignIn(
        name="ИТ-волна", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    store.set_campaign_status(cid, "active")
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="Компрессор для {company_name}",
        body_tmpl="Здравствуйте! Подбор по цеху {company_name}.",
        engagement_gate="all", include_legal=True))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=1, delay_hours=48,
        subject_tmpl="Ре: подбор для {company_name}",
        body_tmpl="Напоминаю про подбор, {company_name}.",
        engagement_gate="all", include_legal=True))
    rids = {}
    for email_addr in emails:
        rid = store.upsert_recipient(RecipientIn(
            email=email_addr, domain=email_addr.split("@")[1],
            company_name=f"Завод {email_addr.split('@')[0].upper()}"))
        store.set_recipient_validation(rid, valid_status="valid", mx_provider="other")
        rids[email_addr] = rid
    return cid, rids


def _inject_inbound(imap, raw: bytes, dedup_key: str, mailbox_id="box1@rusprom.ru"):
    ev = imap.classify(raw)
    ev = replace(ev, dedup_key=dedup_key, mailbox_id=mailbox_id)
    imap._process_event(ev, mailbox_id)
    return ev


@pytest.fixture(scope="module")
def scenario(smtp_sandbox, tmp_path_factory):
    """Прогоняет сквозной сценарий один раз; тесты ниже ассертят его фазы."""
    handler, port = smtp_sandbox
    tmp_path = tmp_path_factory.mktemp("sandbox")
    orch, store, imap, warm_leads = _build_tree(tmp_path, port)
    orch.bootstrap()

    emails = ["dead@corp-a.example", "warm@corp-b.example", "clean@corp-c.example"]
    cid, rids = _seed_campaign(store, emails)
    orch.active_campaign_ids = [cid]

    baseline = len(handler.messages)
    tick1 = orch.tick(now=T0)
    wave1 = handler.messages[baseline:]

    # --- bounce: DSN 5.1.1 на письмо dead@ --------------------------------
    def _sent_rfc_id(email_addr):
        row = store._conn.execute(
            "SELECT rfc_message_id FROM messages WHERE recipient_id=? AND status='sent'",
            (rids[email_addr],),
        ).fetchone()
        return row["rfc_message_id"] if row else None

    dsn_raw = (
        "From: MAILER-DAEMON@corp-a.example\r\n"
        "To: box1@rusprom.ru\r\n"
        "Subject: Delivery Status Notification (Failure)\r\n"
        f"In-Reply-To: {_sent_rfc_id('dead@corp-a.example')}\r\n"
        "Status: 5.1.1\r\n"
        "\r\n"
        "5.1.1 no such user dead@corp-a.example\r\n"
    ).encode()
    _inject_inbound(imap, dsn_raw, "imap:1:101:dsn")

    # --- reply: живой ответ от warm@ --------------------------------------
    reply_raw = (
        "From: warm@corp-b.example\r\n"
        "To: box1@rusprom.ru\r\n"
        "Subject: Re: Компрессор\r\n"
        f"In-Reply-To: {_sent_rfc_id('warm@corp-b.example')}\r\n"
        "\r\n"
        "Интересно, пришлите расчёт на 10 бар.\r\n"
    ).encode()
    _inject_inbound(imap, reply_raw, "imap:1:102:reply")

    # --- вторая волна: только clean@ должен получить касание 2 ------------
    baseline2 = len(handler.messages)
    tick2 = orch.tick(now=T1)
    wave2 = handler.messages[baseline2:]

    return {
        "handler": handler, "store": store, "orch": orch, "cid": cid,
        "rids": rids, "tick1": tick1, "tick2": tick2,
        "wave1": wave1, "wave2": wave2, "warm_leads": warm_leads,
    }


# --------------------------------------------------------------------------
# Фаза 1: волна
# --------------------------------------------------------------------------

def test_wave1_planned_and_sent(scenario):
    """Касание 1 запланировано и доставлено всем трём валидным получателям."""
    t = scenario["tick1"]
    assert t.planned == 6      # 3 получателя × 2 шага в очереди
    assert t.sent == 3         # due сейчас — только step-0
    assert t.failed == 0
    to_addrs = [r for _, rcpts, _ in scenario["wave1"] for r in rcpts]
    assert sorted(to_addrs) == [
        "clean@corp-c.example", "dead@corp-a.example", "warm@corp-b.example"]


def test_wave1_has_unsubscribe_and_legal(scenario):
    """RFC 8058: заголовки one-click в каждом письме; персонализация подставлена."""
    for _, _, content in scenario["wave1"]:
        text = content.decode("utf-8", "replace")
        assert "List-Unsubscribe:" in text
        assert "List-Unsubscribe-Post: List-Unsubscribe=One-Click" in text
        assert "Завод " in text  # {company_name} заполнен, не сырой плейсхолдер


# --------------------------------------------------------------------------
# Фаза 2: bounce → suppression, reply → стоп цепочки
# --------------------------------------------------------------------------

def test_hard_bounce_suppressed(scenario):
    store = scenario["store"]
    hit = store.suppression_lookup(
        email="dead@corp-a.example", domain="corp-a.example", inn=None)
    assert hit is not None and hit.reason == "bounce_hard"


def test_reply_pushed_warm_lead(scenario):
    leads = scenario["warm_leads"]
    assert len(leads) == 1
    assert leads[0][0] == "warm@corp-b.example"
    assert "10 бар" in leads[0][2]


def test_wave2_only_clean_recipient(scenario):
    """Касание 2: bounced и replied исключены на уровне claim (БД), не if-ами."""
    to_addrs = [r for _, rcpts, _ in scenario["wave2"] for r in rcpts]
    assert to_addrs == ["clean@corp-c.example"]
    assert scenario["tick2"].sent == 1


def test_wave2_dedup_no_replan(scenario):
    """Повторное планирование той же кампании не создаёт дублей (ON CONFLICT)."""
    assert scenario["tick2"].planned == 0


def test_no_duplicate_deliveries_total(scenario):
    """За весь сценарий ни один адрес не получил одно письмо дважды."""
    seen = {}
    for _, rcpts, content in scenario["wave1"] + scenario["wave2"]:
        for r in rcpts:
            key = (r, content.split(b"Subject:")[1][:60] if b"Subject:" in content else b"")
            seen[key] = seen.get(key, 0) + 1
    assert all(v == 1 for v in seen.values())


# --------------------------------------------------------------------------
# Фаза 3: резюм после рестарта (отдельная база)
# --------------------------------------------------------------------------

def test_resume_after_restart(smtp_sandbox, tmp_path):
    """Упали посреди отправки ('sending' завис) → новый процесс recover_stale
    возвращает письмо в 'scheduled' и волна дошивается без дублей."""
    handler, port = smtp_sandbox
    orch, store, imap, _ = _build_tree(tmp_path, port, db_name="resume.db")
    orch.bootstrap()
    cid, rids = _seed_campaign(store, ["solo@corp-r.example"])
    orch.active_campaign_ids = [cid]

    # план без отправки: планируем через cadence и claim'им вручную = «упали
    # после claim, до send» (статус sending, письмо не ушло)
    for m in orch.cadence.plan_campaign(cid, now=T0):
        store.enqueue_message(m)
    claimed = store.claim_due_messages(
        now=T0, mailbox_ids=["box1@rusprom.ru", "box2@rusprom.ru"], limit=10)
    assert len(claimed) == 1
    assert store.get_message(claimed[0].id).status == "sending"

    # «рестарт»: новое дерево на ТОЙ ЖЕ базе
    store.close()
    orch2, store2, _, _ = _build_tree(tmp_path, port, db_name="resume.db")
    orch2.lease_ttl_sec = 0  # для теста: lease истёк мгновенно
    orch2.active_campaign_ids = [cid]
    orch2.bootstrap()
    assert store2.get_message(claimed[0].id).status == "scheduled"

    baseline = len(handler.messages)
    tick = orch2.tick(now=T0)
    delivered = [r for _, rcpts, _ in handler.messages[baseline:] for r in rcpts]
    assert tick.sent == 1
    assert delivered == ["solo@corp-r.example"]
    assert store2.get_message(claimed[0].id).status == "sent"
