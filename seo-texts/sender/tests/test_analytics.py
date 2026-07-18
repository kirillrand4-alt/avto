"""Тесты для sender.analytics.

Используем реальный sender.store.Store на временном sqlite-файле (tmp_path).
Цель: поймать регрессы на стыке analytics-store, которые моки скрывали.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.analytics import (  # noqa: E402
    Analytics,
    CampaignReport,
    GlobalReport,
    MailboxReport,
    RateSnapshot,
    ValidationError,
    WarmupReport,
)
from sender.store import (  # noqa: E402
    Campaign,
    CampaignIn,
    EventIn,
    MailboxState,
    MessageIn,
    RecipientIn,
    SequenceStep,
    SequenceStepIn,
    Store,
    WarmupState,
)


@pytest.fixture
def store(tmp_path):
    """Реальный Store с временной sqlite базой."""
    db = Store(str(tmp_path / "test_analytics.db"))
    db.init_schema()
    return db


@pytest.fixture
def analytics(store):
    """Analytics поверх реального store."""
    return Analytics(store)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --------------------------------------------------------------------------- #
# rates() — 4 scope + ValidationError
# --------------------------------------------------------------------------- #


def test_rates_campaign_scope(store, analytics):
    """rates(scope='campaign') считает события по campaign_id."""
    # Кампания 1: 10 sent, 1 bounce, 0 complaint
    cid1 = store.create_campaign(CampaignIn(name="C1", legal_entity="ООО Руспром", legal_inn="7707083893"))
    rid1 = store.upsert_recipient(
        RecipientIn(email="a@x.ru", domain="x.ru")
    )
    
    now = _now()
    for i in range(10):
        store.append_event(
            EventIn(
                dedup_key=f"c1-sent-{i}",
                event_type="sent",
                recipient_id=rid1,
                campaign_id=cid1,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="c1-bounce-1",
            event_type="bounce",
            recipient_id=rid1,
            campaign_id=cid1,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )

    snap = analytics.rates(scope="campaign", target=cid1)
    assert snap.scope == "campaign"
    assert snap.target == str(cid1)
    assert snap.sent == 10
    assert snap.bounce == 1
    assert snap.complaint == 0
    assert snap.bounce_rate == 10.0  # 1/10 * 100
    assert snap.complaint_rate == 0.0


def test_rates_domain_scope(store, analytics):
    """rates(scope='domain') фильтрует события по домену получателя."""
    rid1 = store.upsert_recipient(
        RecipientIn(email="a@foo.com", domain="foo.com")
    )
    rid2 = store.upsert_recipient(
        RecipientIn(email="b@bar.com", domain="bar.com")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    now = _now()
    # foo.com: 5 sent, 2 complaint
    for i in range(5):
        store.append_event(
            EventIn(
                dedup_key=f"foo-sent-{i}",
                event_type="sent",
                recipient_id=rid1,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"foo-complaint-{i}",
                event_type="complaint",
                recipient_id=rid1,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    # bar.com: 3 sent
    for i in range(3):
        store.append_event(
            EventIn(
                dedup_key=f"bar-sent-{i}",
                event_type="sent",
                recipient_id=rid2,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    snap_foo = analytics.rates(scope="domain", target="foo.com")
    assert snap_foo.sent == 5
    assert snap_foo.complaint == 2
    assert snap_foo.complaint_rate == 40.0  # 2/5*100

    snap_bar = analytics.rates(scope="domain", target="bar.com")
    assert snap_bar.sent == 3
    assert snap_bar.complaint == 0
    assert snap_bar.complaint_rate == 0.0


def test_rates_mailbox_scope(store, analytics):
    """rates(scope='mailbox') фильтрует по mailbox_id."""
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    now = _now()
    # mb1: 4 sent, 1 reply
    for i in range(4):
        store.append_event(
            EventIn(
                dedup_key=f"mb1-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="mb1-reply-1",
            event_type="reply",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )
    # mb2: 2 sent
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"mb2-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb2",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    snap_mb1 = analytics.rates(scope="mailbox", target="mb1")
    assert snap_mb1.sent == 4
    assert snap_mb1.reply == 1
    assert snap_mb1.reply_rate == 25.0

    snap_mb2 = analytics.rates(scope="mailbox", target="mb2")
    assert snap_mb2.sent == 2
    assert snap_mb2.reply == 0


def test_rates_global_scope(store, analytics):
    """rates(scope='global') считает все события без фильтров."""
    rid1 = store.upsert_recipient(
        RecipientIn(email="a@x.ru", domain="x.ru")
    )
    rid2 = store.upsert_recipient(
        RecipientIn(email="b@y.com", domain="y.com")
    )
    cid1 = store.create_campaign(CampaignIn(name="C1", legal_entity="ООО Руспром", legal_inn="7707083893"))
    cid2 = store.create_campaign(CampaignIn(name="C2", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    now = _now()
    # C1: 6 sent, 1 bounce
    for i in range(6):
        store.append_event(
            EventIn(
                dedup_key=f"c1-sent-{i}",
                event_type="sent",
                recipient_id=rid1,
                campaign_id=cid1,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="c1-bounce",
            event_type="bounce",
            recipient_id=rid1,
            campaign_id=cid1,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )
    # C2: 4 sent, 2 bounce
    for i in range(4):
        store.append_event(
            EventIn(
                dedup_key=f"c2-sent-{i}",
                event_type="sent",
                recipient_id=rid2,
                campaign_id=cid2,
                mailbox_id="mb2",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"c2-bounce-{i}",
                event_type="bounce",
                recipient_id=rid2,
                campaign_id=cid2,
                mailbox_id="mb2",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    snap = analytics.rates(scope="global", target="*")
    assert snap.scope == "global"
    assert snap.sent == 10
    assert snap.bounce == 3
    assert snap.bounce_rate == 30.0


def test_rates_unknown_scope_raises(analytics):
    """rates() с неизвестным scope вызывает ValidationError."""
    with pytest.raises(ValidationError, match="unknown rates scope"):
        analytics.rates(scope="unicorn", target="123")


def test_rates_campaign_bool_target_raises(analytics):
    """rates(scope='campaign') с bool-значением target вызывает ValidationError."""
    with pytest.raises(ValidationError, match="must be an int, not bool"):
        analytics.rates(scope="campaign", target=True)


def test_rates_campaign_invalid_target_raises(analytics):
    """rates(scope='campaign') с нечисловым target вызывает ValidationError."""
    with pytest.raises(ValidationError, match="must be an int id"):
        analytics.rates(scope="campaign", target="not-a-number")


def test_rates_campaign_non_positive_raises(analytics):
    """rates(scope='campaign') с неположительным id вызывает ValidationError."""
    with pytest.raises(ValidationError, match="must be positive"):
        analytics.rates(scope="campaign", target=0)


def test_rates_mailbox_empty_target_raises(analytics):
    """rates(scope='mailbox') с пустой строкой target вызывает ValidationError."""
    with pytest.raises(ValidationError, match="must be a non-empty str"):
        analytics.rates(scope="mailbox", target="")


def test_rates_domain_non_string_raises(analytics):
    """rates(scope='domain') с не-строковым target вызывает ValidationError."""
    with pytest.raises(ValidationError, match="must be a non-empty str"):
        analytics.rates(scope="domain", target=123)


# --------------------------------------------------------------------------- #
# Деноминатор sent=0 → rate=0.0
# --------------------------------------------------------------------------- #


def test_rates_zero_sent_gives_zero_rate(store, analytics):
    """При sent=0 все rates должны быть 0.0, без деления на ноль."""
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    
    # Добавляем bounce без sent
    store.append_event(
        EventIn(
            dedup_key="bounce-orphan",
            event_type="bounce",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=_now(),
            detail=None,
        )
    )

    snap = analytics.rates(scope="campaign", target=cid)
    assert snap.sent == 0
    assert snap.bounce == 1
    assert snap.bounce_rate == 0.0


# --------------------------------------------------------------------------- #
# Округление до 4 знаков
# --------------------------------------------------------------------------- #


def test_rates_precision_four_decimals(store, analytics):
    """rates округляет процент до 4 знаков после запятой."""
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    
    now = _now()
    # 7 sent, 2 bounce → 2/7*100 = 28.571428... → должно быть 28.5714
    for i in range(7):
        store.append_event(
            EventIn(
                dedup_key=f"sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"bounce-{i}",
                event_type="bounce",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    snap = analytics.rates(scope="campaign", target=cid)
    assert snap.bounce_rate == 28.5714


# --------------------------------------------------------------------------- #
# campaign_report() — 6 типов событий + by_step
# --------------------------------------------------------------------------- #


def test_campaign_report_all_event_types(store, analytics):
    """campaign_report() считает все 6 типов событий."""
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    
    now = _now()
    # 10 sent, 8 delivered, 1 bounce, 1 complaint, 2 reply, 1 unsubscribe
    for i in range(10):
        store.append_event(
            EventIn(
                dedup_key=f"sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    for i in range(8):
        store.append_event(
            EventIn(
                dedup_key=f"delivered-{i}",
                event_type="delivered",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="bounce-1",
            event_type="bounce",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )
    store.append_event(
        EventIn(
            dedup_key="complaint-1",
            event_type="complaint",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"reply-{i}",
                event_type="reply",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="unsub-1",
            event_type="unsubscribe",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )

    rep = analytics.campaign_report(cid)
    assert rep.campaign_id == cid
    assert rep.sent == 10
    assert rep.delivered == 8
    assert rep.bounced == 1
    assert rep.complaints == 1
    assert rep.replies == 2
    assert rep.unsubscribes == 1
    assert rep.bounce_rate == 10.0
    assert rep.complaint_rate == 10.0
    assert rep.reply_rate == 20.0


def test_campaign_report_by_step(store, analytics):
    """campaign_report().by_step раскладывает события по шагам через messages."""
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    
    # Два шага
    step0_id = store.add_step(
        SequenceStepIn(
            campaign_id=cid,
            step_index=0,
            subject_tmpl="Step 0",
            body_tmpl="Body 0",
            delay_hours=0,
        )
    )
    step1_id = store.add_step(
        SequenceStepIn(
            campaign_id=cid,
            step_index=1,
            subject_tmpl="Step 1",
            body_tmpl="Body 1",
            delay_hours=24,
        )
    )

    now = _now()
    # Сообщения (по одному на шаг: join events.message_id -> messages.sequence_step_id)
    msg0_id, _ = store.enqueue_message(
        MessageIn(
            idempotency_key=f"{cid}:{rid}:{step0_id}",
            campaign_id=cid,
            recipient_id=rid,
            sequence_step_id=step0_id,
            scheduled_at=now,
        )
    )
    msg1_id, _ = store.enqueue_message(
        MessageIn(
            idempotency_key=f"{cid}:{rid}:{step1_id}",
            campaign_id=cid,
            recipient_id=rid,
            sequence_step_id=step1_id,
            scheduled_at=now,
        )
    )

    # События: step0 → 3 sent, 1 bounce; step1 → 2 sent
    for i in range(3):
        store.append_event(
            EventIn(
                dedup_key=f"step0-sent-{i}",
                event_type="sent",
                message_id=msg0_id,
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="step0-bounce",
            event_type="bounce",
            message_id=msg0_id,
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=now,
            detail=None,
        )
    )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"step1-sent-{i}",
                event_type="sent",
                message_id=msg1_id,
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    rep = analytics.campaign_report(cid)
    assert len(rep.by_step) == 2
    
    snap0 = rep.by_step[0]
    assert snap0.scope == "step"
    assert snap0.sent == 3
    assert snap0.bounce == 1
    assert snap0.bounce_rate == pytest.approx(33.3333, rel=1e-3)

    snap1 = rep.by_step[1]
    assert snap1.sent == 2
    assert snap1.bounce == 0


# --------------------------------------------------------------------------- #
# mailbox_report() — счётчики из mailbox_state + rates из журнала
# --------------------------------------------------------------------------- #


def test_mailbox_report_with_state(store, analytics):
    """mailbox_report() берёт sent_today/sent_total из mailbox_state, rates из событий."""
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    # Mailbox state
    store.upsert_mailbox_state(
        MailboxState(
            mailbox_id="mb1",
            provider="test",
            sent_today=5,
            sent_total=100,
            ramp_day=3,
            daily_limit=50,
            paused=False,
            pause_reason=None,
            last_sent_at=_now(),
            day_key=_now().strftime("%Y-%m-%d"),
        )
    )

    # События: 10 sent, 2 bounce
    now = _now()
    for i in range(10):
        store.append_event(
            EventIn(
                dedup_key=f"mb1-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )
    for i in range(2):
        store.append_event(
            EventIn(
                dedup_key=f"mb1-bounce-{i}",
                event_type="bounce",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    rep = analytics.mailbox_report("mb1")
    assert rep.mailbox_id == "mb1"
    assert rep.sent_today == 5
    assert rep.sent_total == 100
    assert rep.ramp_day == 3
    assert rep.daily_limit == 50
    assert rep.bounce_rate == 20.0  # 2/10*100
    assert rep.paused is False


def test_mailbox_report_without_state(store, analytics):
    """mailbox_report() для несуществующего mailbox_state возвращает нули."""
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    # События есть, но mailbox_state нет
    now = _now()
    for i in range(3):
        store.append_event(
            EventIn(
                dedup_key=f"orphan-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="orphan",
                provider="test",
                event_ts=now,
                detail=None,
            )
        )

    rep = analytics.mailbox_report("orphan")
    assert rep.mailbox_id == "orphan"
    assert rep.sent_today == 0
    assert rep.sent_total == 0
    assert rep.ramp_day == 0
    assert rep.daily_limit == 0
    assert rep.paused is False


def test_mailbox_report_since_filters_events(store, analytics):
    """mailbox_report(since=) фильтрует события по времени."""
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    old = _now() - timedelta(days=10)
    recent = _now() - timedelta(hours=1)
    
    # Старое событие (до окна)
    store.append_event(
        EventIn(
            dedup_key="old-sent",
            event_type="sent",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=old,
            detail=None,
        )
    )
    store.append_event(
        EventIn(
            dedup_key="old-bounce",
            event_type="bounce",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=old,
            detail=None,
        )
    )
    # Недавнее (в окне)
    for i in range(5):
        store.append_event(
            EventIn(
                dedup_key=f"recent-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=recent,
                detail=None,
            )
        )

    cutoff = _now() - timedelta(days=5)
    rep = analytics.mailbox_report("mb1", since=cutoff)
    # Должны учесться только 5 sent из recent
    assert rep.bounce_rate == 0.0  # старый bounce отфильтрован


# --------------------------------------------------------------------------- #
# warmup_report()
# --------------------------------------------------------------------------- #


def test_warmup_report_with_state(store, analytics):
    """warmup_report() возвращает данные из warmup_state."""
    # FK: warmup_state.mailbox_id ссылается на mailbox_state — строка нужна первой
    store.upsert_mailbox_state(
        MailboxState(
            mailbox_id="mb1",
            provider="test",
            day_key=_now().strftime("%Y-%m-%d"),
            sent_today=0,
            sent_total=0,
            ramp_day=7,
            daily_limit=30,
            last_sent_at=None,
            paused=False,
            pause_reason=None,
        )
    )
    store.upsert_warmup_state(
        WarmupState(
            mailbox_id="mb1",
            phase="active",
            ramp_day=7,
            warmup_sent_today=15,
            reputation_score=0.95,
            warmup_target=20,
            last_warmup_at=_now(),
            day_key=_now().strftime("%Y-%m-%d"),
        )
    )

    rep = analytics.warmup_report("mb1")
    assert rep.mailbox_id == "mb1"
    assert rep.phase == "active"
    assert rep.ramp_day == 7
    assert rep.warmup_sent_today == 15
    assert rep.reputation_score == 0.95


def test_warmup_report_without_state(store, analytics):
    """warmup_report() для ящика без warmup_state возвращает phase='none'."""
    rep = analytics.warmup_report("unknown")
    assert rep.mailbox_id == "unknown"
    assert rep.phase == "none"
    assert rep.ramp_day == 0
    assert rep.warmup_sent_today == 0
    assert rep.reputation_score is None


# --------------------------------------------------------------------------- #
# global_report() — окно since, активные/паузные ящики
# --------------------------------------------------------------------------- #


def test_global_report_all_mailboxes(store, analytics):
    """global_report() считает активные и паузные ящики."""
    store.upsert_mailbox_state(
        MailboxState(
            mailbox_id="mb1",
            provider="test",
            sent_today=10,
            sent_total=100,
            ramp_day=5,
            daily_limit=50,
            paused=False,
            pause_reason=None,
            last_sent_at=_now(),
            day_key=_now().strftime("%Y-%m-%d"),
        )
    )
    store.upsert_mailbox_state(
        MailboxState(
            mailbox_id="mb2",
            provider="test",
            sent_today=0,
            sent_total=50,
            ramp_day=2,
            daily_limit=30,
            paused=True,
            pause_reason="high bounce",
            last_sent_at=_now(),
            day_key=_now().strftime("%Y-%m-%d"),
        )
    )
    store.upsert_mailbox_state(
        MailboxState(
            mailbox_id="mb3",
            provider="test",
            sent_today=5,
            sent_total=200,
            ramp_day=10,
            daily_limit=100,
            paused=False,
            pause_reason=None,
            last_sent_at=_now(),
            day_key=_now().strftime("%Y-%m-%d"),
        )
    )

    rep = analytics.global_report()
    assert rep.active_mailboxes == 2
    assert rep.paused_mailboxes == 1


def test_global_report_since_filters(store, analytics):
    """global_report(since=) фильтрует события по времени (регресс-тест)."""
    rid = store.upsert_recipient(
        RecipientIn(email="x@y.ru", domain="y.ru")
    )
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО Руспром", legal_inn="7707083893"))
    
    old = _now() - timedelta(days=20)
    recent = _now() - timedelta(hours=2)
    
    # Старые события (до окна)
    for i in range(10):
        store.append_event(
            EventIn(
                dedup_key=f"old-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=old,
                detail=None,
            )
        )
    for i in range(5):
        store.append_event(
            EventIn(
                dedup_key=f"old-bounce-{i}",
                event_type="bounce",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=old,
                detail=None,
            )
        )
    # Недавние (в окне)
    for i in range(3):
        store.append_event(
            EventIn(
                dedup_key=f"recent-sent-{i}",
                event_type="sent",
                recipient_id=rid,
                campaign_id=cid,
                mailbox_id="mb1",
                provider="test",
                event_ts=recent,
                detail=None,
            )
        )
    store.append_event(
        EventIn(
            dedup_key="recent-bounce-0",
            event_type="bounce",
            recipient_id=rid,
            campaign_id=cid,
            mailbox_id="mb1",
            provider="test",
            event_ts=recent,
            detail=None,
        )
    )

    # Без окна — всё: 13 sent, 6 bounce
    rep_all = analytics.global_report()
    assert rep_all.total_sent == 13
    assert rep_all.total_bounced == 6

    # Окно сутки — только недавние: 3 sent, 1 bounce.
    # До фикса _as_since это окно молча игнорировалось (регресс-тест).
    rep = analytics.global_report(since=_now() - timedelta(days=1))
    assert rep.total_sent == 3
    assert rep.total_bounced == 1
    assert rep.global_bounce_rate == pytest.approx(33.3333, abs=0.001)
