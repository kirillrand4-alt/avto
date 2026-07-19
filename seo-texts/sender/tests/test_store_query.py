"""Тесты NEW-BACKEND методов Store (Фаза 2.1): сегментация базы, чтение
журнала/кампаний/сообщений, история переписки, аудит suppression.
Реальный Store на временной sqlite.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import (  # noqa: E402
    Store, RecipientIn, CampaignIn, SequenceStepIn, MessageIn, EventIn,
    SuppressionIn, Event,
)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "q.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def seeded(store):
    """Двое получателей: mail.ru (valid, под suppression) и yandex (invalid)."""
    r1 = store.upsert_recipient(RecipientIn(
        email="lead@mail.ru", domain="mail.ru", inn="7701234567",
        company_name="Альфа Пром", okved="28.13", segment="prom"))
    r2 = store.upsert_recipient(RecipientIn(
        email="dir@yandex.ru", domain="yandex.ru", inn="7709876543",
        company_name="Бета Сервис"))
    store.set_recipient_validation(r1, valid_status="valid", mx_provider="mailru")
    store.set_recipient_validation(r2, valid_status="invalid", mx_provider="yandex")
    store.suppression_add(SuppressionIn(scope="email", value="lead@mail.ru", reason="complaint"))
    cid = store.create_campaign(CampaignIn(name="Кампания-1", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    return store, r1, r2, cid


# ---- query_recipients / count_recipients ----

def test_query_by_valid_status(seeded):
    store, r1, r2, _ = seeded
    got = store.query_recipients({"valid_status": "valid"})
    assert [r.email for r in got] == ["lead@mail.ru"]


def test_query_by_provider_list(seeded):
    store, *_ = seeded
    got = store.query_recipients({"provider": ["mailru", "yandex"]})
    assert len(got) == 2


def test_query_domain_like_and_inn(seeded):
    store, *_ = seeded
    assert [r.email for r in store.query_recipients({"domain_like": "yandex"})] == ["dir@yandex.ru"]
    assert [r.email for r in store.query_recipients({"inn": "7701234567"})] == ["lead@mail.ru"]


def test_query_okved_prefix_and_company(seeded):
    store, *_ = seeded
    assert [r.email for r in store.query_recipients({"okved_prefix": "28"})] == ["lead@mail.ru"]
    assert [r.email for r in store.query_recipients({"company_like": "Бета"})] == ["dir@yandex.ru"]


def test_query_suppressed_flag(seeded):
    store, *_ = seeded
    assert [r.email for r in store.query_recipients({"suppressed": True})] == ["lead@mail.ru"]
    assert [r.email for r in store.query_recipients({"suppressed": False})] == ["dir@yandex.ru"]


def test_query_limit_offset_order(seeded):
    store, *_ = seeded
    page1 = store.query_recipients({}, limit=1, offset=0, order_by="email")
    page2 = store.query_recipients({}, limit=1, offset=1, order_by="email")
    assert page1[0].email == "dir@yandex.ru"  # алфавит: dir < lead
    assert page2[0].email == "lead@mail.ru"


def test_query_order_by_whitelist(seeded):
    store, *_ = seeded
    # инъекция в order_by игнорируется — падаем на дефолт id, не на ошибку SQL
    got = store.query_recipients({}, order_by="id; DROP TABLE recipients")
    assert len(got) == 2


def test_count_recipients_breakdown(seeded):
    store, *_ = seeded
    c = store.count_recipients({})
    assert c["total"] == 2
    assert c["by_status"] == {"valid": 1, "invalid": 1}
    assert c["by_provider"] == {"mailru": 1, "yandex": 1}


def test_count_with_filter(seeded):
    store, *_ = seeded
    assert store.count_recipients({"valid_status": "valid"})["total"] == 1


# ---- list_events / get_thread ----

def test_list_events_and_filters(seeded):
    store, r1, r2, cid = seeded
    now = datetime.now(timezone.utc)
    store.append_event(EventIn(dedup_key="s1", event_type="sent", event_ts=now,
                               recipient_id=r1, campaign_id=cid, provider="mailru"))
    store.append_event(EventIn(dedup_key="b1", event_type="bounce", event_ts=now,
                               recipient_id=r1, campaign_id=cid, provider="mailru"))
    store.append_event(EventIn(dedup_key="s2", event_type="sent", event_ts=now,
                               recipient_id=r2, campaign_id=cid, provider="yandex"))
    assert len(store.list_events(campaign_id=cid)) == 3
    assert len(store.list_events(event_type="sent")) == 2
    assert len(store.list_events(event_type=["sent", "bounce"])) == 3
    assert len(store.list_events(provider="yandex")) == 1
    assert all(isinstance(e, Event) for e in store.list_events())


def test_list_events_since(seeded):
    store, r1, _, cid = seeded
    old = datetime.now(timezone.utc) - timedelta(days=10)
    recent = datetime.now(timezone.utc)
    store.append_event(EventIn(dedup_key="old", event_type="sent", event_ts=old,
                               recipient_id=r1, campaign_id=cid))
    store.append_event(EventIn(dedup_key="new", event_type="sent", event_ts=recent,
                               recipient_id=r1, campaign_id=cid))
    assert len(store.list_events(since=datetime.now(timezone.utc) - timedelta(days=1))) == 1


def test_get_thread_chronology(seeded):
    store, r1, _, cid = seeded
    t0 = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
    store.append_event(EventIn(dedup_key="a", event_type="reply", event_ts=t0 + timedelta(hours=2),
                               recipient_id=r1, campaign_id=cid))
    store.append_event(EventIn(dedup_key="b", event_type="sent", event_ts=t0,
                               recipient_id=r1, campaign_id=cid))
    thread = store.get_thread(r1, cid)
    assert [e.event_type for e in thread] == ["sent", "reply"]  # ASC


# ---- list_campaigns / list_messages ----

def test_list_campaigns_status(seeded):
    store, _, _, cid = seeded
    c2 = store.create_campaign(CampaignIn(name="К2", legal_entity="ООО", legal_inn="1"))
    store.set_campaign_status(c2, "active")
    assert len(store.list_campaigns()) == 2
    assert [c.name for c in store.list_campaigns(status="active")] == ["К2"]


def test_list_messages(seeded):
    store, r1, _, cid = seeded
    sid = store.add_step(SequenceStepIn(campaign_id=cid, step_index=0, delay_hours=0,
                                        subject_tmpl="s", body_tmpl="b"))
    store.enqueue_message(MessageIn(idempotency_key="k1", campaign_id=cid, recipient_id=r1,
                                    sequence_step_id=sid, scheduled_at=datetime.now(timezone.utc)))
    msgs = store.list_messages(campaign_id=cid)
    assert len(msgs) == 1 and msgs[0].recipient_id == r1


# ---- iter/count/remove suppression ----

def test_iter_suppression_filters(seeded):
    store, *_ = seeded
    store.suppression_add(SuppressionIn(scope="domain", value="x.ru", reason="competitor"))
    assert len(store.iter_suppression()) == 2
    assert len(store.iter_suppression(scope="email")) == 1
    assert len(store.iter_suppression(reason="competitor")) == 1


def test_count_suppression(seeded):
    store, *_ = seeded
    c = store.count_suppression()
    assert c["total"] == 1 and c["by_scope"] == {"email": 1}
    assert c["active"] == 1 and c["expired"] == 0


def test_count_suppression_expired(seeded):
    store, *_ = seeded
    past = datetime.now(timezone.utc) - timedelta(days=1)
    store.suppression_add(SuppressionIn(scope="domain", value="y.ru", reason="manual", expires_at=past))
    c = store.count_suppression()
    assert c["total"] == 2 and c["active"] == 1 and c["expired"] == 1


def test_suppression_remove_audited(seeded):
    store, *_ = seeded
    sid = store.iter_suppression()[0].id
    assert store.suppression_remove(sid, reason="ошибочная жалоба", actor="kirill") is True
    assert store.count_suppression()["total"] == 0
    # аудит в consent_log
    hist = store.consent_history("lead@mail.ru")
    assert hist[-1]["action"] == "suppression_removed"
    assert hist[-1]["detail"]["reason"] == "ошибочная жалоба"


def test_suppression_remove_missing(seeded):
    store, *_ = seeded
    assert store.suppression_remove(424242, reason="x") is False
