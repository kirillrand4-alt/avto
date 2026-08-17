"""Кнопка «в автоотправку» (владелец 06.08): store-методы и цикл AutoSendLoop.

Проверяю ПОВЕДЕНИЕ, а не наличие кода:

  * claim_approved_due берёт ТОЛЬКО одобренные+созревшие письма — обычные
    scheduled (не одобренные) остаются очереди подтверждений;
  * текст в отправку идёт из review (правка оператора приоритетнее шаблона);
  * вне окна получателя письмо НЕ шлётся — возвращается в scheduled на слот;
  * выключенный тумблер auto_send_enabled = цикл ничего не трогает;
  * next_slot держит час В ЗОНЕ ПОЛУЧАТЕЛЯ (Владивосток ≠ Москва).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.auto_send import (AutoSendLoop, next_slot,  # noqa: E402
                              within_window_now)
from sender.dtos import (CampaignIn, MessageIn, RecipientIn,  # noqa: E402
                         SequenceStepIn)
from sender.store import Store  # noqa: E402

ОКНО = {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "18:00",
        "tz": "Europe/Moscow", "by_recipient_tz": True}
# Среда 2026-08-05: 12:00 МСК = 19:00 Владивостока (окно уже закрыто)
СРЕДА_12_МСК = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "b.db"))
    s.init_schema()
    yield s
    s.close()


def _письмо(store, *, email="a@zavod.ru", tz="Europe/Moscow",
            review_status="pending", scheduled=None, subject="Тема из review",
            body="Тело из review", edited_subject=None, edited_body=None):
    """Получатель + кампания + шаг + письмо + review; вернуть (mid, rid)."""
    rid_rec = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[-1], inn=None, tz=tz))
    cid = store.create_campaign(CampaignIn(
        name=f"к-{email}", legal_entity="ООО Руспром", legal_inn="1"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="{subject}", body_tmpl="{body}"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"t-{email}", campaign_id=cid, recipient_id=rid_rec,
        sequence_step_id=sid,
        scheduled_at=scheduled or (СРЕДА_12_МСК - timedelta(hours=1))))
    rid, _ = store.confirm_submit(
        email=email, subject=subject, body=body, campaign_id=cid,
        recipient_id=rid_rec, message_id=mid)
    if review_status != "pending":
        store.confirm_decide(rid, status=review_status, decided_by="тест",
                             edited_subject=edited_subject,
                             edited_body=edited_body)
    return mid, rid


# ---- store ---------------------------------------------------------------- #

def test_claim_beret_tolko_odobrennye(store):
    mid_ok, _ = _письмо(store, email="da@z.ru", review_status="approved")
    mid_net, _ = _письмо(store, email="net@z.ru", review_status="pending")
    got = store.claim_approved_due(now=СРЕДА_12_МСК, limit=10)
    assert [m.id for m in got] == [mid_ok]
    # одобренное захвачено, неодобренное не тронуто
    assert store.get_message(mid_ok).status == "sending"
    assert store.get_message(mid_net).status == "scheduled"
    # повторный claim пуст (lease)
    assert store.claim_approved_due(now=СРЕДА_12_МСК, limit=10) == []


def test_claim_ne_beret_nesozrevshie(store):
    _письмо(store, email="rano@z.ru", review_status="approved",
            scheduled=СРЕДА_12_МСК + timedelta(hours=3))
    assert store.claim_approved_due(now=СРЕДА_12_МСК, limit=10) == []


def test_review_for_message_i_privyazka(store):
    mid, rid = _письмо(store, email="link@z.ru")
    row = store.confirm_review_for_message(mid)
    assert row and row["id"] == rid
    # привязка новой карточки к письму: только pending и только пустая
    rid2, _ = store.confirm_submit(email="x@y.ru", subject="s", body="b")
    store.confirm_set_message(rid2, mid)
    with pytest.raises(Exception):
        store.confirm_set_message(rid2, mid)  # уже привязана


def test_reschedule(store):
    mid, _ = _письмо(store, email="slot@z.ru", review_status="approved")
    later = СРЕДА_12_МСК + timedelta(days=1)
    assert store.reschedule_message(mid, later)
    assert store.claim_approved_due(now=СРЕДА_12_МСК, limit=10) == []
    assert [m.id for m in store.claim_approved_due(now=later, limit=10)] == [mid]


# ---- окно в зоне получателя ------------------------------------------------ #

def test_okno_vladivostok():
    """12:00 МСК среды: Москве можно, Владивостоку (19:00) уже нельзя."""
    assert within_window_now(ОКНО, "Europe/Moscow", СРЕДА_12_МСК)
    assert not within_window_now(ОКНО, "Asia/Vladivostok", СРЕДА_12_МСК)
    слот = next_slot(ОКНО, "Asia/Vladivostok", СРЕДА_12_МСК)
    местное = слот.astimezone(ZoneInfo("Asia/Vladivostok"))
    assert (местное.date(), местное.hour) == (
        (СРЕДА_12_МСК + timedelta(days=1)).date(), 9)


def test_slot_vnutri_okna_eto_now():
    assert next_slot(ОКНО, "Europe/Moscow", СРЕДА_12_МСК) == СРЕДА_12_МСК


def test_slot_pyatnitsa_vecher_perenositsya_na_ponedelnik():
    пятница_вечер = datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc)  # 21:00 МСК
    слот = next_slot(ОКНО, "Europe/Moscow", пятница_вечер)
    местное = слот.astimezone(ZoneInfo("Europe/Moscow"))
    assert местное.isoweekday() == 1 and местное.hour == 9


# ---- цикл ------------------------------------------------------------------ #

class _Отправка:
    """Мок живого Sender: помнит, что ушло."""

    def __init__(self):
        self.sent = []

    def pick_mailbox(self, recipient, campaign, *, now=None, manual=False,
                     message=None):
        return "mb1"

    def send(self, message, rendered, mailbox_id, *, now=None, to_email=None,
             manual=False, force=False):
        self.sent.append((message.id, rendered.subject, rendered.body, to_email))

        class R:
            ok = True
            error = None
        return R()


class _Конфиг:
    def sending_window(self):
        raise RuntimeError("окно берём из override")

    def get(self, key, default=None):
        return default


def _цикл(store, sender):
    store.set_setting("sending_window", dict(ОКНО))
    store.set_setting("auto_send_enabled", True)
    return AutoSendLoop(store=store, config=_Конфиг(), live_sender=sender)


def test_tsikl_shlet_tekst_iz_review(store):
    mid, _ = _письмо(store, email="live@z.ru", review_status="edited",
                     edited_subject="Правка темы", edited_body="Правка тела")
    s = _Отправка()
    out = _цикл(store, s).tick(now=СРЕДА_12_МСК)
    assert out["sent"] == 1
    assert s.sent == [(mid, "Правка темы", "Правка тела", "live@z.ru")]


def test_tsikl_spit_bez_tumblera(store):
    _письмо(store, email="hold@z.ru", review_status="approved")
    s = _Отправка()
    loop = _цикл(store, s)
    store.set_setting("auto_send_enabled", False)
    assert loop.tick(now=СРЕДА_12_МСК) == {
        "sent": 0, "released": 0, "skipped": 0, "failed": 0}
    assert s.sent == []


def test_tsikl_ne_shlet_noch_poluchatelya(store):
    """Владивосток в 19:00 местного: письмо НЕ уходит, переезжает на утро."""
    mid, _ = _письмо(store, email="dv@z.ru", tz="Asia/Vladivostok",
                     review_status="approved")
    s = _Отправка()
    out = _цикл(store, s).tick(now=СРЕДА_12_МСК)
    assert out == {"sent": 0, "released": 1, "skipped": 0, "failed": 0}
    assert s.sent == []
    m = store.get_message(mid)
    assert m.status == "scheduled"
    местное = m.scheduled_at.astimezone(ZoneInfo("Asia/Vladivostok"))
    assert местное.hour == 9  # ближайшее утро получателя
