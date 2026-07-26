"""Задача 1: ядро confirm-send — очередь, решения, диф, durable, заслоны.

Проверяем инварианты ТЗ (ENGINEER-TASKS-CONFIRM-SEND):
  * идемпотентность по (ИНН, email, campaign_id);
  * durable: решения переживают рестарт (новый Store на том же файле);
  * approved/edited переводят письмо pending_review -> scheduled (и НИКОГДА
    не шлют SMTP — холд);
  * edited хранит правку И unified-диф (золотые пары);
  * stoplist пишет suppression (конкурент -> ещё и ИНН-scope);
  * заслоны: suppression и повторный контакт <90 дн — на этапе очереди
    (авто-skip) И на этапе подтверждения (approve блокируется);
  * sample-режим: каждое N-е письмо в очередь, пропущенные — bypassed (след).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.confirm import (  # noqa: E402
    ConfirmBlockedError, ConfirmSend, build_diff,
)
from sender.dtos import CampaignIn, MessageIn, RecipientIn  # noqa: E402
from sender.errors import ValidationError  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

UTC = timezone.utc


class _Cfg:
    """Минимальный конфиг: только dotted get()."""

    def __init__(self, **kv):
        self._kv = kv

    def get(self, key, default=None):
        return self._kv.get(key, default)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "confirm.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def suppression(store):
    return Suppression(store)


def make_confirm(store, suppression, mode="all", every=3):
    return ConfirmSend(
        _Cfg(**{"confirm.mode": mode, "confirm.sample_every": every}),
        store, suppression)


def seed_message(store, email="lead@zavod.ru", inn="4201000625"):
    cid = store.create_campaign(CampaignIn(
        name="Калибровка", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    from sender.dtos import SequenceStepIn
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[1], inn=inn))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"cal:{email}", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)),
        status="pending_review")
    return cid, rid, mid


# --------------------------------------------------------------------------- #
# Очередь: постановка, идемпотентность, durable
# --------------------------------------------------------------------------- #
def test_submit_pending_and_idempotent(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r1 = cs.submit(email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
                   recipient_id=rid, message_id=mid,
                   subject="Тема", body="Тело", panel={"score": 72})
    assert r1.status == "pending" and r1.created
    # Повторный submit того же письма — тот же review, без дублей.
    r2 = cs.submit(email="LEAD@zavod.ru", inn="4201 000625", campaign_id=cid,
                   subject="Тема", body="Тело")
    assert r2.review_id == r1.review_id and not r2.created

    row = cs.get(r1.review_id)
    assert row["status"] == "pending"
    assert row["panel"] == {"score": 72}
    # письмо стоит в pending_review и claim его НЕ берёт
    assert store.get_message(mid).status == "pending_review"
    claimed = store.claim_due_messages(
        now=datetime.now(UTC) + timedelta(hours=1),
        mailbox_ids=["box1@rusprom.ru"], limit=10)
    assert claimed == []


def test_mode_off_bypasses(store, suppression):
    cs = make_confirm(store, suppression, mode="off")
    r = cs.submit(email="a@b.ru", subject="s", body="b")
    assert r.status == "bypassed" and r.review_id == 0
    assert store.confirm_counts() == {}


def test_decisions_survive_restart(tmp_path, suppression):
    """Durable: решения переживают рестарт процесса (новый Store, тот же файл)."""
    db = str(tmp_path / "durable.db")
    s1 = Store(db)
    s1.init_schema()
    cs1 = ConfirmSend(_Cfg(**{"confirm.mode": "all"}), s1, Suppression(s1))
    cid, rid, mid = seed_message(s1)
    r = cs1.submit(email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
                   message_id=mid, subject="Тема", body="Тело")
    assert cs1.approve(r.review_id, operator="kirill")
    s1.close()

    s2 = Store(db)  # «рестарт»
    s2.init_schema()
    row = s2.confirm_get(r.review_id)
    assert row["status"] == "approved" and row["decided_by"] == "kirill"
    assert s2.get_message(mid).status == "scheduled"
    s2.close()


# --------------------------------------------------------------------------- #
# Решения
# --------------------------------------------------------------------------- #
def test_approve_releases_message_no_smtp(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", campaign_id=cid, message_id=mid,
                  subject="Тема", body="Тело")
    assert cs.approve(r.review_id, operator="op")
    assert store.get_message(mid).status == "scheduled"  # в очередь, не в SMTP
    # Повторное решение идемпотентно (не перерешивается).
    assert cs.approve(r.review_id) is False


def test_edit_saves_diff_golden_pair(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", campaign_id=cid, message_id=mid,
                  subject="Компрессор для завода", body="Здравствуйте!\nСтарый текст.")
    assert cs.edit(r.review_id, body="Здравствуйте!\nНовый текст.", operator="op")
    row = cs.get(r.review_id)
    assert row["status"] == "edited"
    assert row["edited_body"] == "Здравствуйте!\nНовый текст."
    assert "-Старый текст." in row["diff_text"]
    assert "+Новый текст." in row["diff_text"]
    # письмо ушло в очередь с ПРАВЛЕНЫМ текстом
    msg = store.get_message(mid)
    assert msg.status == "scheduled"
    assert msg.body_rendered == "Здравствуйте!\nНовый текст."
    # золотые пары отдаются для калибровки
    pairs = cs.golden_pairs()
    assert len(pairs) == 1 and pairs[0]["diff"] == row["diff_text"]


def test_edit_without_changes_is_approve(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", campaign_id=cid, message_id=mid,
                  subject="Т", body="Б")
    assert cs.edit(r.review_id, subject="Т", body="Б")
    assert cs.get(r.review_id)["status"] == "approved"


def test_skip_requires_reason(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", campaign_id=cid, message_id=mid,
                  subject="Т", body="Б")
    with pytest.raises(ValidationError):
        cs.skip(r.review_id, reason="  ")
    assert cs.skip(r.review_id, reason="сомнительный повод", operator="op")
    assert store.get_message(mid).status == "skipped"


def test_stoplist_competitor_adds_suppression_email_and_inn(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store, email="rival@comp.ru", inn="7707083893")
    r = cs.submit(email="rival@comp.ru", inn="7707083893", campaign_id=cid,
                  message_id=mid, subject="Т", body="Б")
    assert cs.stoplist(r.review_id, reason="конкурент", operator="op")
    assert store.suppression_lookup(
        email="rival@comp.ru", domain="comp.ru", inn=None) is not None
    assert store.suppression_lookup(
        email="x@y.ru", domain="y.ru", inn="7707083893") is not None
    assert store.get_message(mid).status == "skipped"


def test_stoplist_by_request_is_forever_unsubscribe(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store, email="asked@stop.ru", inn=None)
    r = cs.submit(email="asked@stop.ru", campaign_id=cid, message_id=mid,
                  subject="Т", body="Б")
    assert cs.stoplist(r.review_id, reason="по запросу")
    entry = store.suppression_lookup(
        email="asked@stop.ru", domain="stop.ru", inn=None)
    assert entry.reason == "unsubscribe"  # навсегда, снять нельзя (П1.2)


def test_stoplist_unknown_reason_rejected(store, suppression):
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", campaign_id=cid, message_id=mid,
                  subject="Т", body="Б")
    with pytest.raises(ValidationError):
        cs.stoplist(r.review_id, reason="не нравится")


# --------------------------------------------------------------------------- #
# Заслоны: очередь И подтверждение
# --------------------------------------------------------------------------- #
def test_queue_guard_suppressed_autoskips(store, suppression):
    suppression.add_email("gone@x.ru", "unsubscribe")
    cs = make_confirm(store, suppression)
    r = cs.submit(email="gone@x.ru", subject="Т", body="Б", campaign_id=None)
    assert r.status == "skipped"
    assert "suppressed:unsubscribe" in r.reason
    row = cs.get(r.review_id)
    assert row["status"] == "skipped" and row["reason"].startswith("auto:")


def test_queue_guard_recent_contact_90d(store, suppression):
    store.send_log_add(email="fresh@x.ru", outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=30))
    cs = make_confirm(store, suppression)
    r = cs.submit(email="fresh@x.ru", subject="Т", body="Б")
    assert r.status == "skipped" and "recent_contact<90d" in r.reason
    # а вот контакт старше 90 дней НЕ блокирует
    store.send_log_add(email="old@x.ru", outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=120))
    r2 = cs.submit(email="old@x.ru", subject="Т", body="Б")
    assert r2.status == "pending"


def test_approve_guard_recheck_at_confirmation(store, suppression):
    """Адрес отписался МЕЖДУ постановкой и решением → approve заблокирован,
    письмо остаётся pending (решает оператор: skip/stoplist)."""
    cs = make_confirm(store, suppression)
    cid, rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
                  message_id=mid, subject="Т", body="Б")
    suppression.add_email("lead@zavod.ru", "unsubscribe")
    with pytest.raises(ConfirmBlockedError):
        cs.approve(r.review_id)
    assert cs.get(r.review_id)["status"] == "pending"
    assert store.get_message(mid).status == "pending_review"
    # skip после блокировки работает
    assert cs.skip(r.review_id, reason="отписался в процессе")


def test_approve_force_overrides_guard_and_writes_audit(store, suppression):
    """Решение владельца 26.07: по ВТОРОМУ подтверждению оператора письмо
    уходит вопреки заслону, а сам обход остаётся в аудите."""
    cs = make_confirm(store, suppression)
    cid, _rid, mid = seed_message(store)
    r = cs.submit(email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
                  message_id=mid, subject="Т", body="Б")
    suppression.add_email("lead@zavod.ru", "unsubscribe")
    store.send_log_add(email="lead@zavod.ru", outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=10))
    # без force — по-прежнему блок (заслон не «ослаб» сам по себе)
    with pytest.raises(ConfirmBlockedError):
        cs.approve(r.review_id)
    # с force — решение проходит
    assert cs.approve(r.review_id, operator="kirill", force=True)
    assert cs.get(r.review_id)["status"] == "approved"
    audit = [a for a in store.list_audit(action="confirm_force_send")]
    assert len(audit) == 1
    detail = audit[0]["detail"]
    assert detail["email"] == "lead@zavod.ru"
    assert any("unsubscribe" in str(x) for x in detail["обойдено"])


# --------------------------------------------------------------------------- #
# Sample-режим
# --------------------------------------------------------------------------- #
def test_sample_mode_every_third(store, suppression):
    cs = make_confirm(store, suppression, mode="sample", every=3)
    cid, _rid, _mid = seed_message(store)
    statuses = []
    for i in range(7):
        r = cs.submit(email=f"lead{i}@zavod.ru", campaign_id=cid,
                      subject="Т", body="Б")
        statuses.append(r.status)
    assert statuses == ["pending", "bypassed", "bypassed",
                        "pending", "bypassed", "bypassed", "pending"]
    counts = store.confirm_counts()
    assert counts.get("pending") == 3 and counts.get("bypassed") == 4


def test_build_diff_format():
    d = build_diff("Тема А", "строка1\nстрока2", "Тема Б", "строка1\nстрока3")
    assert "--- original" in d and "+++ edited" in d
    assert "-Тема: Тема А" in d and "+Тема: Тема Б" in d
    assert "-строка2" in d and "+строка3" in d


def test_skip_applies_after_transient_error(tmp_path):
    """Ревью №2: временная ошибка SMTP не должна уводить письмо ручной очереди
    в автоматическую, а «скип» оператора обязан примениться в любом случае."""
    from datetime import datetime, timezone
    from sender.store import Store
    from sender.dtos import CampaignIn, SequenceStepIn, RecipientIn, MessageIn

    st = Store(str(tmp_path / "s.db"))
    st.init_schema()
    cid = st.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = st.add_step(SequenceStepIn(campaign_id=cid, step_index=0, delay_hours=0,
                                     subject_tmpl="s", body_tmpl="b"))
    rid = st.upsert_recipient(RecipientIn(email="a@b.ru", domain="b.ru", inn="7701000001"))
    mid, _ = st.enqueue_message(MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(timezone.utc)),
        status="pending_review")

    # временная ошибка на ручной отправке
    st.mark_failed(mid, "smtp timeout", retryable=True)
    assert st.get_message(mid).status == "pending_review", "письмо уехало в авто-очередь"

    # оператор скипает — решение обязано примениться
    rev, _ = st.confirm_submit(email="a@b.ru", subject="s", body="b", inn="7701000001",
                               campaign_id=cid, recipient_id=rid, message_id=mid)
    st.confirm_decide(rev, status="skipped", reason="не наш профиль")
    assert st.get_message(mid).status == "skipped"


def test_hung_sending_live_returns_to_queue(tmp_path):
    """Ревью №12: панель упала посреди approve — карточка не должна остаться
    в 'sending_live' навсегда и пропасть из очереди оператора."""
    from sender.store import Store

    st = Store(str(tmp_path / "h.db"))
    st.init_schema()
    rev, _ = st.confirm_submit(email="a@b.ru", subject="s", body="b",
                               inn="7701000001", campaign_id=1)
    assert st.confirm_claim_sending(rev) is True
    assert st.confirm_get(rev)["status"] == "sending_live"
    # аренда истекла (эмулируем нулевым TTL)
    freed = st.recover_stale_reviews(lease_ttl_sec=0)
    assert freed == 1
    assert st.confirm_get(rev)["status"] == "pending"
