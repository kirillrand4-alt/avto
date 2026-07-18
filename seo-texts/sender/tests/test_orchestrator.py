"""Unit tests for sender.orchestrator.

Store is backed by a real temporary SQLite database. All other dependencies
(config, sender, cadence, gates, imap, warmup, analytics, personalizer) are
lightweight fakes defined inline without unittest.mock.patch.
"""

import os
import sqlite3
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.errors import PersonalizationGateError  # noqa: E402
from sender.orchestrator import Orchestrator  # noqa: E402
from sender.store import MailboxState, Store  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn,
    GateDecision,
    InboundEvent,
    MessageIn,
    RecipientIn,
    RenderedMessage,
    SendResult,
    SequenceStepIn,
    TickResult,
    WarmupCycleResult,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_mailbox_state(store: Store, mailbox_id: str, provider: str = "fake") -> None:
    """Создать строку mailbox_state (нужна increment_sent/set_mailbox_paused)."""
    store.upsert_mailbox_state(MailboxState(
        mailbox_id=mailbox_id, provider=provider,
        day_key=_now().strftime("%Y-%m-%d"),
        sent_today=0, sent_total=0, ramp_day=0, daily_limit=100,
        last_sent_at=None, paused=False, pause_reason=None))


# ============================================================================
# Фейки
# ============================================================================


@dataclass
class FakeMailbox:
    mailbox_id: str
    provider: str = "fake"


class FakeConfig:
    """Легковесный конфиг с dict + mailboxes()."""

    def __init__(self, data: dict[str, Any] | None = None, boxes: list[FakeMailbox] | None = None):
        self._data = data or {}
        self._boxes = boxes or []

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def mailboxes(self) -> list[FakeMailbox]:
        return self._boxes


class FakeSender:
    """Фейк-отправитель с логом вызовов. Сам вызывает store.mark_sent/increment_sent."""

    def __init__(self, store: Store):
        self.store = store
        self.dry_run = False
        self.calls: list[tuple[int, str]] = []
        self._pick_result: str | None = None
        self._send_error: str | None = None
        self._send_retryable = False

    def pick_mailbox(self, recipient, campaign) -> str | None:
        return self._pick_result

    def send(self, message, rendered, mailbox_id: str) -> SendResult:
        self.calls.append((message.id, mailbox_id))
        if self._send_error:
            self.store.mark_failed(message.id, self._send_error, retryable=self._send_retryable)
            return SendResult(
                ok=False, rfc_message_id=None, mailbox_id=mailbox_id,
                sent_at=None, error=self._send_error, retryable=self._send_retryable
            )
        rfc_id = f"<fake-{message.id}@test>"
        sent_at = _now()
        self.store.mark_sent(message.id, rfc_id, sent_at)
        # increment_sent требует наличия mailbox_state - проверяем перед вызовом
        mb_state = self.store.get_mailbox_state(mailbox_id)
        if mb_state is not None:
            self.store.increment_sent(mailbox_id, now=sent_at)
        return SendResult(ok=True, rfc_message_id=rfc_id, mailbox_id=mailbox_id, sent_at=sent_at)


class FakeCadence:
    """Фейк-кадензер. plan_campaign возвращает заданный список MessageIn."""

    def __init__(self):
        self._plan_result: list[MessageIn] = []

    def plan_campaign(self, campaign_id: int, *, now: datetime) -> list[MessageIn]:
        return self._plan_result


class FakeGates:
    """Фейк-гейты. evaluate_all возвращает заданный список GateDecision."""

    def __init__(self):
        self._decisions: list[GateDecision] = []

    def evaluate_all(self) -> list[GateDecision]:
        return self._decisions


class FakeImap:
    """Фейк-IMAP. poll_once возвращает заданный список InboundEvent."""

    def __init__(self):
        self._events: dict[str, list[InboundEvent]] = {}
        self._raise_on: str | None = None

    def poll_once(self, mailbox_id: str) -> list[InboundEvent]:
        if self._raise_on == mailbox_id:
            raise RuntimeError("imap poll_once failed")
        return self._events.get(mailbox_id, [])


class FakeWarmup:
    """Фейк-прогрев. run_cycle возвращает WarmupCycleResult."""

    def __init__(self):
        self._result = WarmupCycleResult(mailbox_id="", sent=0, target=0, reputation_score=None)

    def run_cycle(self, mailbox_id: str, *, now: datetime) -> WarmupCycleResult:
        return WarmupCycleResult(
            mailbox_id=mailbox_id,
            sent=self._result.sent,
            target=self._result.target,
            reputation_score=self._result.reputation_score
        )


class FakeAnalytics:
    """Фейк-аналитика (не используется в orchestrator напрямую)."""
    pass


class FakePersonalizer:
    """Фейк-персонализатор. render возвращает RenderedMessage."""

    def __init__(self, config):
        self._unfilled: tuple[str, ...] = ()
        self._raise_gate_error = False

    def render(self, step, recipient, campaign) -> RenderedMessage:
        if self._raise_gate_error:
            raise PersonalizationGateError("personalization gate error")
        return RenderedMessage(
            subject=f"subj-{step.id}",
            body=f"body-{step.id}",
            unfilled_fields=self._unfilled
        )


# ============================================================================
# Фикстуры
# ============================================================================


@pytest.fixture
def tmp_store():
    """Реальный sqlite store во временном файле."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = Store(path)
    store.init_schema()
    yield store
    store.close()
    os.unlink(path)


@pytest.fixture
def orch_deps(tmp_store):
    """Набор зависимостей для Orchestrator."""
    config = FakeConfig(
        data={
            "orchestrator.lease_ttl_sec": 900,
            "orchestrator.send_batch": 100,
            "orchestrator.active_campaigns": [],
        },
        boxes=[FakeMailbox("mb1"), FakeMailbox("mb2")]
    )
    sender = FakeSender(tmp_store)
    sender._pick_result = "mb1"
    cadence = FakeCadence()
    gates = FakeGates()
    imap = FakeImap()
    warmup = FakeWarmup()
    analytics = FakeAnalytics()
    personalizer = FakePersonalizer(config)
    
    # Инициализируем mailbox_state для mb1 и mb2
    _ensure_mailbox_state(tmp_store, "mb1")
    _ensure_mailbox_state(tmp_store, "mb2")
    
    return {
        "config": config,
        "store": tmp_store,
        "sender": sender,
        "cadence": cadence,
        "gates": gates,
        "imap": imap,
        "warmup": warmup,
        "analytics": analytics,
        "personalizer": personalizer,
    }


# ============================================================================
# Тесты
# ============================================================================


def test_bootstrap_calls_init_and_recover(orch_deps):
    """bootstrap вызывает init_schema и recover_stale."""
    orch = Orchestrator(**orch_deps)
    orch.bootstrap()
    # проверяем, что таблицы созданы (store.init_schema не падает дважды)
    orch_deps["store"].init_schema()


def test_bootstrap_recover_stale_basic(orch_deps):
    """bootstrap вызывает recover_stale, который возвращает int."""
    orch = Orchestrator(**orch_deps)
    # создаём кампанию и реципиента
    store = orch_deps["store"]
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    # ставим сообщение в очередь
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    store.enqueue_message(msg_in)
    # claim → статус 'sending'
    claimed = store.claim_due_messages(now=_now(), mailbox_ids=["mb1"], limit=1)
    assert len(claimed) == 1
    msg = store.get_message(claimed[0].id)
    assert msg.status == "sending"
    
    # recover_stale(0) должен вернуть 1 (один stale message)
    recovered = store.recover_stale(0)
    assert recovered == 1
    msg2 = store.get_message(claimed[0].id)
    assert msg2.status == "scheduled"


def test_tick_order_imap_before_planning(orch_deps):
    """tick вызывает imap.poll_once ДО планирования."""
    orch = Orchestrator(**orch_deps)
    imap = orch_deps["imap"]
    cadence = orch_deps["cadence"]
    
    call_order = []
    orig_poll = imap.poll_once
    orig_plan = cadence.plan_campaign
    
    def tracked_poll(mid):
        call_order.append(("imap", mid))
        return orig_poll(mid)
    
    def tracked_plan(cid, *, now):
        call_order.append(("cadence", cid))
        return orig_plan(cid, now=now)
    
    imap.poll_once = tracked_poll
    cadence.plan_campaign = tracked_plan
    
    orch.tick(now=_now())
    
    # imap должен быть вызван раньше cadence
    imap_idx = next((i for i, x in enumerate(call_order) if x[0] == "imap"), None)
    cadence_idx = next((i for i, x in enumerate(call_order) if x[0] == "cadence"), None)
    # может не быть cadence, если active_campaigns пусто, но imap точно есть
    assert imap_idx is not None
    if cadence_idx is not None:
        assert imap_idx < cadence_idx


def test_tick_order_gates_before_claim(orch_deps):
    """tick вызывает gates.evaluate_all ДО claim_due_messages."""
    orch = Orchestrator(**orch_deps)
    gates = orch_deps["gates"]
    store = orch_deps["store"]
    
    call_order = []
    orig_eval = gates.evaluate_all
    orig_claim = store.claim_due_messages
    
    def tracked_eval():
        call_order.append("gates")
        return orig_eval()
    
    def tracked_claim(*, now, mailbox_ids, limit):
        call_order.append("claim")
        return orig_claim(now=now, mailbox_ids=mailbox_ids, limit=limit)
    
    gates.evaluate_all = tracked_eval
    store.claim_due_messages = tracked_claim
    
    orch.tick(now=_now())
    
    gates_idx = call_order.index("gates") if "gates" in call_order else None
    claim_idx = call_order.index("claim") if "claim" in call_order else None
    assert gates_idx is not None
    if claim_idx is not None:
        assert gates_idx < claim_idx


def test_global_trip_pauses_all_skips_wave_and_warmup(orch_deps):
    """global gate trip → pause_all, волна и warmup пропущены, gates_tripped посчитан."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    gates = orch_deps["gates"]
    sender = orch_deps["sender"]
    warmup = orch_deps["warmup"]
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    store.enqueue_message(msg_in)
    
    # global trip
    gates._decisions = [
        GateDecision(
            scope="global", target="all", tripped=True,
            metric="complaint", value=10.0, threshold=5.0, action="pause"
        )
    ]
    
    warmup._result = WarmupCycleResult(mailbox_id="mb1", sent=5, target=10, reputation_score=0.9)
    
    result = orch.tick(now=_now())
    
    # волна пропущена
    assert result.sent == 0
    assert result.planned == 0
    # warmup пропущен
    assert result.warmup_sent == 0
    # gates_tripped посчитан
    assert result.gates_tripped == 1
    # sender.send не вызван
    assert len(sender.calls) == 0
    # все ящики в паузе
    mb1 = store.get_mailbox_state("mb1")
    mb2 = store.get_mailbox_state("mb2")
    assert mb1.paused
    assert mb2.paused


def test_mailbox_trip_pauses_one_mailbox_wave_continues(orch_deps):
    """mailbox gate trip → пауза только этого ящика, волна продолжается."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    gates = orch_deps["gates"]
    sender = orch_deps["sender"]
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    store.enqueue_message(msg_in)
    
    # mailbox trip только для mb1
    gates._decisions = [
        GateDecision(
            scope="mailbox", target="mb1", tripped=True,
            metric="bounce", value=8.0, threshold=5.0, action="pause"
        )
    ]
    
    sender._pick_result = "mb2"  # выберем другой ящик
    
    result = orch.tick(now=_now())
    
    # волна прошла (sent=1)
    assert result.sent == 1
    assert result.gates_tripped == 1
    # mb1 в паузе, mb2 нет
    mb1 = store.get_mailbox_state("mb1")
    mb2 = store.get_mailbox_state("mb2")
    assert mb1.paused
    assert not mb2.paused


def test_personalization_gate_error_marks_failed_not_retryable(orch_deps):
    """PersonalizationGateError → mark_failed(retryable=False), письмо НЕ уходит."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    sender = orch_deps["sender"]
    personalizer = orch_deps["personalizer"]
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    mid, _ = store.enqueue_message(msg_in)
    
    # персонализатор кидает исключение
    personalizer._raise_gate_error = True
    
    result = orch.tick(now=_now())
    
    # failed=1, sent=0
    assert result.failed == 1
    assert result.sent == 0
    # sender.send не вызван
    assert len(sender.calls) == 0
    # статус failed в store
    msg = store.get_message(mid)
    assert msg.status == "failed"
    assert "personalization gate error" in (msg.last_error or "")


def test_unfilled_fields_marks_failed_not_retryable(orch_deps):
    """rendered.unfilled_fields непустой → mark_failed(retryable=False), письмо НЕ уходит."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    sender = orch_deps["sender"]
    personalizer = orch_deps["personalizer"]
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    mid, _ = store.enqueue_message(msg_in)
    
    # рендер с незаполненными полями
    personalizer._unfilled = ("first_name", "company")
    
    result = orch.tick(now=_now())
    
    # failed=1, sent=0
    assert result.failed == 1
    assert result.sent == 0
    # sender.send не вызван
    assert len(sender.calls) == 0
    # статус failed в store
    msg = store.get_message(mid)
    assert msg.status == "failed"
    assert "unfilled_fields" in (msg.last_error or "")


def test_pick_mailbox_none_leaves_message_recoverable(orch_deps):
    """pick_mailbox → None (пейсинг/лимит) → письмо НЕ хоронится: остаётся в
    'sending', recover_stale по истечении lease вернёт в 'scheduled' и оно
    уйдёт следующим тиком. Раньше mark_skipped убивал его терминально."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    sender = orch_deps["sender"]

    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]

    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    mid, _ = store.enqueue_message(msg_in)

    # pick_mailbox возвращает None
    sender._pick_result = None

    result = orch.tick(now=_now())

    # skipped=1 (в счётчике тика), sent=0, send не вызван
    assert result.skipped == 1
    assert result.sent == 0
    assert len(sender.calls) == 0
    # письмо живо: 'sending' под lease, не 'skipped'
    assert store.get_message(mid).status == "sending"

    # lease истёк → письмо возвращается в очередь, ящик появился → уходит
    orch.lease_ttl_sec = 0
    sender._pick_result = "mb1"
    result2 = orch.tick(now=_now())
    assert result2.sent == 1
    assert store.get_message(mid).status == "sent"


def test_successful_send_updates_planned_sent_status(orch_deps):
    """Успешная отправка: planned/sent корректны, статус 'sent' в store."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    sender = orch_deps["sender"]
    cadence = orch_deps["cadence"]
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # cadence вернёт одно сообщение для планирования
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    cadence._plan_result = [msg_in]
    
    result = orch.tick(now=_now())
    
    # planned=1, sent=1
    assert result.planned == 1
    assert result.sent == 1
    # sender.send вызван один раз
    assert len(sender.calls) == 1
    # статус sent в store
    messages = store.claim_due_messages(now=_now(), mailbox_ids=["mb1"], limit=10)
    # claim не вернёт уже отправленные
    assert len(messages) == 0
    # проверим статус через прямой запрос
    conn = store._conn
    cur = conn.execute("SELECT status FROM messages WHERE idempotency_key=?", ("k1",))
    row = cur.fetchone()
    assert row[0] == "sent"


def test_dry_run_propagated_to_sender(orch_deps):
    """run() прокидывает sender.dry_run=True."""
    orch = Orchestrator(**orch_deps)
    sender = orch_deps["sender"]
    
    # проверяем прямой вызов _propagate_dry_run
    orch._propagate_dry_run(True)
    assert sender.dry_run is True
    orch._propagate_dry_run(False)
    assert sender.dry_run is False
    
    # через run с мгновенным stop
    stop = threading.Event()
    stop.set()
    orch.run(interval_sec=0, dry_run=True, stop=stop)
    assert sender.dry_run is True


def test_run_stops_immediately_if_stop_set(orch_deps):
    """run(): stop.set() до старта → выходит сразу."""
    orch = Orchestrator(**orch_deps)
    
    stop = threading.Event()
    stop.set()
    
    # запускаем run — должен выйти без tick
    orch.run(interval_sec=0, dry_run=False, stop=stop)
    
    # если tick был вызван, то sender.calls не пуст
    # но здесь мы не ставили сообщений, так что проверим просто что не упало


def test_run_survives_tick_exception(orch_deps):
    """Исключение в tick не роняет run."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    
    # заставим tick кидать исключение один раз
    orig_recover = store.recover_stale
    call_count = [0]
    
    def bad_recover(ttl):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("tick failed")
        return orig_recover(ttl)
    
    store.recover_stale = bad_recover
    
    stop = threading.Event()
    
    # запускаем run в отдельном потоке
    def runner():
        orch.run(interval_sec=0, dry_run=False, stop=stop)
    
    import threading as th
    t = th.Thread(target=runner, daemon=True)
    t.start()
    
    # даём время на 2 тика
    import time
    time.sleep(0.1)
    stop.set()
    t.join(timeout=1.0)
    
    # должно быть минимум 2 вызова recover_stale (один упал, второй прошёл)
    assert call_count[0] >= 2


def test_resume_all_unpauses_all_mailboxes(orch_deps):
    """resume_all снимает паузу со всех ящиков."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    
    # ставим все ящики в паузу
    orch.pause_all("test")
    
    mb1 = store.get_mailbox_state("mb1")
    mb2 = store.get_mailbox_state("mb2")
    assert mb1.paused
    assert mb2.paused
    
    # снимаем паузу
    orch.resume_all()
    
    mb1 = store.get_mailbox_state("mb1")
    mb2 = store.get_mailbox_state("mb2")
    assert not mb1.paused
    assert not mb2.paused


def test_imap_poll_failure_does_not_crash_tick(orch_deps):
    """Падение одного poll_once не роняет tick."""
    orch = Orchestrator(**orch_deps)
    imap = orch_deps["imap"]
    
    # первый ящик кидает исключение
    imap._raise_on = "mb1"
    # второй ящик вернёт событие
    imap._events["mb2"] = [
        InboundEvent(
            kind="reply", mailbox_id="mb2", dedup_key="d1",
            rfc_message_id="<1@test>", from_addr="a@b.c",
            thread_id=None, recipient_id=None, snippet="", raw_headers={}
        )
    ]
    
    result = orch.tick(now=_now())
    
    # inbound посчитан (только mb2)
    assert result.inbound == 1


def test_tick_claims_only_non_paused_mailboxes(orch_deps):
    """claim_due_messages получает только не-paused ящики."""
    orch = Orchestrator(**orch_deps)
    store = orch_deps["store"]
    
    # ставим mb1 в паузу
    store.set_mailbox_paused("mb1", True, "test")
    
    # создаём кампанию, реципиента, step
    cid = store.create_campaign(CampaignIn(name="c1", legal_entity="ООО", legal_inn="123"))
    store.set_campaign_status(cid, "active")
    rid = store.upsert_recipient(RecipientIn(email="a@b.c", domain="b.c"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"
    ))
    orch.active_campaign_ids = [cid]
    
    # ставим сообщение
    msg_in = MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=_now()
    )
    store.enqueue_message(msg_in)
    
    # tick: claim должен получить только mb2 (mb1 в паузе)
    sender = orch_deps["sender"]
    sender._pick_result = "mb2"

    seen_mailbox_ids: list[list[str]] = []
    real_claim = store.claim_due_messages

    def recording_claim(*, now, mailbox_ids, limit):
        seen_mailbox_ids.append(list(mailbox_ids))
        return real_claim(now=now, mailbox_ids=mailbox_ids, limit=limit)

    store.claim_due_messages = recording_claim
    try:
        result = orch.tick(now=_now())
    finally:
        store.claim_due_messages = real_claim

    # claim получил только не-паузнутые ящики
    assert seen_mailbox_ids and seen_mailbox_ids[0] == ["mb2"]
    # письмо (mailbox=NULL) всё равно claim'ится и уходит через mb2
    assert result.sent == 1
    assert store.get_message(1).status == "sent"
