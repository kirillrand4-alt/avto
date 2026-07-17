# FILE: sender/tests/test_store.py
"""Юнит-тесты store.py: happy-path, границы, инварианты безопасности.

Используем реальную временную SQLite (per-test), сети/внешних зависимостей нет.
"""

import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# Подключаем каталог sender/ в путь и импортируем модуль напрямую.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store import (  # noqa: E402
    CampaignIn,
    EventIn,
    MailboxState,
    MessageIn,
    RecipientIn,
    SequenceStepIn,
    Store,
    StoreError,
    SuppressionIn,
    WarmupState,
)

UTC = timezone.utc


def _dt(y=2025, mo=1, d=10, h=12, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def _idem(campaign_id, recipient_id, step_index):
    raw = f"{campaign_id}|{recipient_id}|{step_index}".encode()
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    s.init_schema()
    yield s
    s.close()


@pytest.fixture()
def base(store):
    """Готовит кампанию, шаг и получателя, возвращает id-шники."""
    rid = store.upsert_recipient(
        RecipientIn(email="lead@acme.ru", domain="acme.ru", inn="7712345678")
    )
    cid = store.create_campaign(
        CampaignIn(name="Q1", legal_entity="ООО Руспром", legal_inn="7700000000")
    )
    sid = store.add_step(
        SequenceStepIn(
            campaign_id=cid,
            step_index=0,
            delay_hours=0,
            subject_tmpl="s",
            body_tmpl="b",
            include_legal=True,
        )
    )
    return {"rid": rid, "cid": cid, "sid": sid, "store": store}


# --------------------------------------------------------------------------- #
# schema / recipients
# --------------------------------------------------------------------------- #


def test_init_schema_idempotent(tmp_path):
    s = Store(tmp_path / "x.db")
    s.init_schema()
    s.init_schema()  # повторный вызов не падает
    # PRAGMA foreign_keys включён
    assert s._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    s.close()


def test_upsert_recipient_dedup_and_update(store):
    r1 = store.upsert_recipient(RecipientIn(email="a@b.ru", domain="b.ru"))
    r2 = store.upsert_recipient(
        RecipientIn(email="a@b.ru", domain="b.ru", company_name="Beta", inn="7701")
    )
    assert r1 == r2  # UNIQUE(email) → тот же id
    rec = store.get_recipient(r1)
    assert rec.company_name == "Beta"
    assert rec.inn == "7701"


def test_upsert_recipient_preserves_existing_on_null(store):
    rid = store.upsert_recipient(
        RecipientIn(email="a@b.ru", domain="b.ru", company_name="Beta")
    )
    # повторный upsert без company_name не должен затирать существующее
    store.upsert_recipient(RecipientIn(email="a@b.ru", domain="b.ru"))
    assert store.get_recipient(rid).company_name == "Beta"


def test_bulk_upsert_and_iter(store):
    n = store.bulk_upsert_recipients(
        [
            RecipientIn(email="a@b.ru", domain="b.ru"),
            RecipientIn(email="c@d.ru", domain="d.ru"),
        ]
    )
    assert n == 2
    assert len(list(store.iter_recipients())) == 2
    # фильтр по valid_status: по умолчанию 'unknown'
    assert len(list(store.iter_recipients(valid_status="unknown"))) == 2
    assert len(list(store.iter_recipients(valid_status="valid"))) == 0


def test_get_recipient_missing(store):
    assert store.get_recipient(999) is None


# --------------------------------------------------------------------------- #
# campaigns / steps
# --------------------------------------------------------------------------- #


def test_campaign_lifecycle(store):
    cid = store.create_campaign(
        CampaignIn(name="Q1", legal_entity="ООО Руспром", legal_inn="7700000000",
                   config={"k": "v"})
    )
    c = store.get_campaign(cid)
    assert c.status == "draft"
    assert c.config == {"k": "v"}
    assert c.started_at is None

    store.set_campaign_status(cid, "active")
    c2 = store.get_campaign(cid)
    assert c2.status == "active"
    assert c2.started_at is not None


def test_steps_ordered_and_unique(base):
    store, cid = base["store"], base["cid"]
    store.add_step(
        SequenceStepIn(campaign_id=cid, step_index=1, delay_hours=48,
                       subject_tmpl="s2", body_tmpl="b2")
    )
    steps = store.get_steps(cid)
    assert [s.step_index for s in steps] == [0, 1]
    assert steps[0].include_legal is True
    # повтор step_index → нарушение UNIQUE
    with pytest.raises(Exception):
        store.add_step(
            SequenceStepIn(campaign_id=cid, step_index=0, delay_hours=1,
                           subject_tmpl="x", body_tmpl="y")
        )


# --------------------------------------------------------------------------- #
# messages / idempotency
# --------------------------------------------------------------------------- #


def _enqueue(base, when=None, **kw):
    store = base["store"]
    when = when or _dt()
    return store.enqueue_message(
        MessageIn(
            idempotency_key=kw.get("key", _idem(base["cid"], base["rid"], 0)),
            campaign_id=base["cid"],
            recipient_id=base["rid"],
            sequence_step_id=base["sid"],
            scheduled_at=when,
        )
    )


def test_enqueue_idempotent(base):
    mid1, created1 = _enqueue(base)
    mid2, created2 = _enqueue(base)
    assert created1 is True
    assert created2 is False  # тот же idempotency_key
    assert mid1 == mid2


def test_claim_due_only(base):
    store = base["store"]
    # одно due, одно в будущем
    _enqueue(base, when=_dt(h=9), key=_idem(base["cid"], base["rid"], 0))
    rid2 = store.upsert_recipient(RecipientIn(email="l2@acme.ru", domain="acme.ru"))
    store.enqueue_message(
        MessageIn(
            idempotency_key=_idem(base["cid"], rid2, 0),
            campaign_id=base["cid"], recipient_id=rid2,
            sequence_step_id=base["sid"], scheduled_at=_dt(h=23),
        )
    )
    claimed = store.claim_due_messages(now=_dt(h=10), mailbox_ids=["box1@rusprom.ru"], limit=10)
    assert len(claimed) == 1
    assert claimed[0].status == "sending"
    assert claimed[0].claimed_at is not None
    # повторный claim не выдаёт уже 'sending'
    again = store.claim_due_messages(now=_dt(h=10), mailbox_ids=["box1@rusprom.ru"], limit=10)
    assert again == []


def test_claim_respects_limit(base):
    store = base["store"]
    for i in range(5):
        rid = store.upsert_recipient(RecipientIn(email=f"u{i}@acme.ru", domain="acme.ru"))
        store.enqueue_message(
            MessageIn(idempotency_key=_idem(base["cid"], rid, 0),
                      campaign_id=base["cid"], recipient_id=rid,
                      sequence_step_id=base["sid"], scheduled_at=_dt(h=9))
        )
    claimed = store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=2)
    assert len(claimed) == 2


def test_claim_excludes_suppressed(base):
    """Инвариант suppression-first: claim не выдаёт саппрессированного получателя."""
    store = base["store"]
    _enqueue(base, when=_dt(h=9))
    store.suppression_add(SuppressionIn(scope="email", value="lead@acme.ru", reason="unsubscribe"))
    claimed = store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=10)
    assert claimed == []


def test_claim_excludes_suppressed_by_domain(base):
    store = base["store"]
    _enqueue(base, when=_dt(h=9))
    store.suppression_add(SuppressionIn(scope="domain", value="acme.ru", reason="competitor"))
    assert store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=10) == []


def test_claim_ignores_expired_suppression(base):
    store = base["store"]
    _enqueue(base, when=_dt(h=9))
    store.suppression_add(
        SuppressionIn(scope="email", value="lead@acme.ru", reason="bounce_hard",
                      expires_at=_dt(2020, 1, 1))
    )
    claimed = store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=10)
    assert len(claimed) == 1  # suppression истекла → доступен


def test_claim_excludes_replied(base):
    """Инвариант «не слать ответившему»: reply-событие исключает получателя."""
    store = base["store"]
    _enqueue(base, when=_dt(h=9))
    store.append_event(
        EventIn(dedup_key="imap:1:1:reply", event_type="reply", event_ts=_dt(h=8),
                recipient_id=base["rid"], campaign_id=base["cid"])
    )
    assert store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=10) == []
    assert store.has_reply(base["rid"], base["cid"]) is True


def test_claim_empty_mailboxes_allows_unassigned(base):
    store = base["store"]
    _enqueue(base, when=_dt(h=9))
    # unassigned mailbox_id (NULL) допускается даже при пустом наборе
    claimed = store.claim_due_messages(now=_dt(h=10), mailbox_ids=[], limit=10)
    assert len(claimed) == 1


# --------------------------------------------------------------------------- #
# mark_* и резюм
# --------------------------------------------------------------------------- #


def test_mark_sent(base):
    store = base["store"]
    mid, _ = _enqueue(base, when=_dt(h=9))
    store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=1)
    store.mark_sent(mid, "rfc-123@rusprom.ru", _dt(h=10, mi=1))
    m = store.get_message(mid)
    assert m.status == "sent"
    assert m.rfc_message_id == "rfc-123@rusprom.ru"
    assert store.find_message_by_rfc_id("rfc-123@rusprom.ru").id == mid


def test_mark_failed_retryable_goes_back_to_scheduled(base):
    store = base["store"]
    mid, _ = _enqueue(base, when=_dt(h=9))
    store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=1)
    store.mark_failed(mid, "smtp timeout", retryable=True)
    m = store.get_message(mid)
    assert m.status == "scheduled"
    assert m.claimed_at is None
    assert m.attempt_count == 1
    # снова claimable
    assert len(store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=1)) == 1


def test_mark_failed_permanent(base):
    store = base["store"]
    mid, _ = _enqueue(base, when=_dt(h=9))
    store.mark_failed(mid, "bad recipient", retryable=False)
    assert store.get_message(mid).status == "failed"


def test_mark_skipped(base):
    store = base["store"]
    mid, _ = _enqueue(base, when=_dt(h=9))
    store.mark_skipped(mid, "replied")
    m = store.get_message(mid)
    assert m.status == "skipped"
    assert m.last_error == "replied"


def test_recover_stale(base):
    """Резюм: зависшие 'sending' со старым lease → 'scheduled'."""
    store = base["store"]
    mid, _ = _enqueue(base, when=_dt(h=9))
    store.claim_due_messages(now=_dt(h=10), mailbox_ids=["m"], limit=1)
    assert store.get_message(mid).status == "sending"
    # claimed_at был выставлен на _dt(h=10) (в прошлом) → recover_stale его вернёт
    n = store.recover_stale(lease_ttl_sec=60)
    assert n == 1
    assert store.get_message(mid).status == "scheduled"


# --------------------------------------------------------------------------- #
# events
# --------------------------------------------------------------------------- #


def test_append_event_dedup(base):
    store = base["store"]
    id1, c1 = store.append_event(
        EventIn(dedup_key="send:1", event_type="sent", event_ts=_dt(),
                campaign_id=base["cid"], recipient_id=base["rid"])
    )
    id2, c2 = store.append_event(
        EventIn(dedup_key="send:1", event_type="sent", event_ts=_dt(),
                campaign_id=base["cid"], recipient_id=base["rid"])
    )
    assert c1 is True and c2 is False
    assert id1 == id2  # повторный поллинг не задваивает


def test_count_events_filters(base):
    store = base["store"]
    store.append_event(EventIn(dedup_key="e1", event_type="bounce", event_ts=_dt(h=8),
                               campaign_id=base["cid"], recipient_id=base["rid"]))
    store.append_event(EventIn(dedup_key="e2", event_type="bounce", event_ts=_dt(h=12),
                               campaign_id=base["cid"], recipient_id=base["rid"]))
    store.append_event(EventIn(dedup_key="e3", event_type="sent", event_ts=_dt(h=12),
                               campaign_id=base["cid"], recipient_id=base["rid"]))
    assert store.count_events(event_type="bounce", campaign_id=base["cid"]) == 2
    assert store.count_events(event_type="bounce", domain="acme.ru") == 2
    assert store.count_events(event_type="bounce", since=_dt(h=10)) == 1
    assert store.count_events(event_type="sent") == 1


def test_has_reply_false(base):
    assert base["store"].has_reply(base["rid"], base["cid"]) is False


# --------------------------------------------------------------------------- #
# suppression
# --------------------------------------------------------------------------- #


def test_suppression_add_idempotent(store):
    id1, c1 = store.suppression_add(SuppressionIn(scope="domain", value="x.ru", reason="competitor"))
    id2, c2 = store.suppression_add(SuppressionIn(scope="domain", value="x.ru", reason="manual"))
    assert c1 is True and c2 is False
    assert id1 == id2


def test_suppression_lookup_order(store):
    store.suppression_add(SuppressionIn(scope="domain", value="acme.ru", reason="competitor"))
    # email не в списке, но домен — да
    hit = store.suppression_lookup(email="lead@acme.ru", domain="acme.ru", inn="7712")
    assert hit is not None
    assert hit.scope == "domain"
    # ничего не совпадает
    assert store.suppression_lookup(email="a@b.ru", domain="b.ru", inn=None) is None


def test_suppression_lookup_expired(store):
    store.suppression_add(
        SuppressionIn(scope="email", value="a@b.ru", reason="bounce_hard",
                      expires_at=_dt(2020, 1, 1))
    )
    assert store.suppression_lookup(email="a@b.ru", domain="b.ru", inn=None) is None


# --------------------------------------------------------------------------- #
# mailbox / warmup state
# --------------------------------------------------------------------------- #


def _mstate(**kw):
    defaults = dict(
        mailbox_id="box1@rusprom.ru", provider="yandex", day_key="2025-01-10",
        sent_today=0, sent_total=0, ramp_day=0, daily_limit=8,
        last_sent_at=None, paused=False, pause_reason=None,
    )
    defaults.update(kw)
    return MailboxState(**defaults)


def test_mailbox_state_upsert_get(store):
    store.upsert_mailbox_state(_mstate())
    st = store.get_mailbox_state("box1@rusprom.ru")
    assert st.provider == "yandex"
    assert st.daily_limit == 8
    assert st.paused is False


def test_increment_sent_same_day(store):
    store.upsert_mailbox_state(_mstate())
    st = store.increment_sent("box1@rusprom.ru", now=_dt(2025, 1, 10, 11))
    assert st.sent_today == 1
    assert st.sent_total == 1
    assert st.ramp_day == 0
    st2 = store.increment_sent("box1@rusprom.ru", now=_dt(2025, 1, 10, 12))
    assert st2.sent_today == 2
    assert st2.sent_total == 2


def test_increment_sent_day_rollover(store):
    """Смена day_key: sent_today сброшен, ramp_day инкрементирован."""
    store.upsert_mailbox_state(_mstate(sent_today=5, sent_total=5))
    st = store.increment_sent("box1@rusprom.ru", now=_dt(2025, 1, 11, 9))
    assert st.day_key == "2025-01-11"
    assert st.sent_today == 1     # сброс + текущая отправка
    assert st.sent_total == 6     # total персистентен
    assert st.ramp_day == 1       # +1 к рампу


def test_increment_sent_missing_raises(store):
    with pytest.raises(StoreError):
        store.increment_sent("nope@rusprom.ru", now=_dt())


def test_set_mailbox_paused(store):
    store.upsert_mailbox_state(_mstate())
    store.set_mailbox_paused("box1@rusprom.ru", True, "gate_complaint")
    st = store.get_mailbox_state("box1@rusprom.ru")
    assert st.paused is True
    assert st.pause_reason == "gate_complaint"


def test_warmup_state_roundtrip(store):
    store.upsert_mailbox_state(_mstate(mailbox_id="box5@rusprom.ru", provider="google"))
    store.upsert_warmup_state(
        WarmupState(mailbox_id="box5@rusprom.ru", phase="ramp", ramp_day=1,
                    warmup_target=3, warmup_sent_today=0, reputation_score=0.8,
                    day_key="2025-01-10", last_warmup_at=None)
    )
    w = store.get_warmup_state("box5@rusprom.ru")
    assert w.phase == "ramp"
    assert w.reputation_score == 0.8
    assert store.get_warmup_state("absent") is None


# --------------------------------------------------------------------------- #
# transaction
# --------------------------------------------------------------------------- #


def test_transaction_rollback(store):
    store.upsert_recipient(RecipientIn(email="a@b.ru", domain="b.ru"))
    with pytest.raises(RuntimeError):
        with store.transaction() as conn:
            conn.execute(
                "INSERT INTO recipients (email, domain, valid_status, created_at, updated_at) "
                "VALUES ('c@d.ru','d.ru','unknown','2025-01-10T00:00:00.000000','2025-01-10T00:00:00.000000')"
            )
            raise RuntimeError("boom")
    # изменение не сохранилось
    assert len(list(store.iter_recipients())) == 1
