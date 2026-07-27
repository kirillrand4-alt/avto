"""Ветка переписки в очереди подтверждений (баг владельца 2026-07-27:
«и тут письмо обрезанное, вся цепочка не разворачивается»).

Проверяем ровно три симптома и их причины:
  1) входящее приходило коротким огрызком — тело должно уходить на фронт
     ЦЕЛИКОМ (до DIALOG_BODY_MAX), а обрезка — быть явной (body_truncated);
  2) наши письма показывались одной темой без текста: body_rendered пишет
     только confirm_decide на approved/edited, а у живой отправки и у ОТВЕТА
     клиенту строки messages либо пустые, либо их нет вовсе — тело лежит в
     confirm_reviews;
  3) цепочка не разворачивалась целиком: лимит отрезал СВЕЖИЕ письма, а пустая
     ветка по ИНН не откатывалась на ветку контакта.

Сети и провайдерского API здесь нет: реальный Store на временной sqlite и
фейковые deps для HTTP-маршрута.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dtos import (  # noqa: E402
    CampaignIn, EventIn, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.store import DIALOG_BODY_MAX, Store  # noqa: E402

UTC = timezone.utc
# Реальное «сейчас», а не фикс-дата: confirm_decide ставит decided_at по часам
# машины, и синтетический календарь ломал бы хронологию ленты.
NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
ИНН = "7701234567"


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "dialog.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def база(store):
    """Компания с одним контактом и кампанией — минимум для ленты."""
    rid = store.upsert_recipient(RecipientIn(
        email="snab@zavod.ru", domain="zavod.ru", inn=ИНН,
        company_name="Завод"))
    cid = store.create_campaign(CampaignIn(
        name="К1", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    return store, rid, cid, sid


def _входящее(store, rid, snippet, *, ts=NOW, key="in1", subject="Re: КП"):
    store.append_event(EventIn(
        dedup_key=key, event_type="reply", event_ts=ts, recipient_id=rid,
        mailbox_id="box1@ru", detail={"snippet": snippet,
                                      "headers": {"Subject": subject},
                                      "reply_kind": "interested"}))


def _наше_письмо(store, rid, cid, sid, *, body, subject="КП по компрессорам",
                 ts=NOW, key="k1"):
    """Письмо, отправленное ВЖИВУЮ из панели: messages.subject/body_rendered
    остаются пустыми (confirm_decide на 'sent' их не пишет), текст — в
    confirm_reviews."""
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=key, campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=ts))
    review_id, _ = store.confirm_submit(
        email="snab@zavod.ru", subject=subject, body=body, inn=ИНН,
        campaign_id=cid, recipient_id=rid, message_id=mid,
        dedup_key=f"live|{key}")
    store.confirm_decide(review_id, status="sent", decided_by="owner")
    store.mark_sent(mid, f"<{key}@ru>", ts, mailbox_id="box1@ru")
    store.send_log_add(email="snab@zavod.ru", inn=ИНН, ts=ts, message_id=mid,
                       rfc_message_id=f"<{key}@ru>", subject=subject)
    return mid


def _наш_ответ(store, rid, *, body, subject="Ваш запрос", ts=NOW, key="r1"):
    """Ответ клиенту: строки messages НЕТ вообще (sender.send_reply пишет
    только send_log), полный текст — в confirm_reviews."""
    review_id, _ = store.confirm_submit(
        email="snab@zavod.ru", subject=subject, body=body, inn=ИНН,
        recipient_id=rid, kind="reply", thread_id="t1", dedup_key=f"reply|{key}")
    store.confirm_decide(review_id, status="sent", decided_by="owner")
    store.send_log_add(email="snab@zavod.ru", inn=ИНН, ts=ts,
                       rfc_message_id=f"<{key}@ru>", subject="Re: " + subject,
                       outcome="reply_sent")
    return review_id


# ---- симптом 1: входящее целиком ---------------------------------------- #

def test_входящее_приходит_целиком(база):
    store, rid, *_ = база
    текст = "Здравствуйте! " + "нам нужен компрессор винтовой. " * 120
    _входящее(store, rid, текст)
    (item,) = store.dialog_thread(rid)
    assert item["direction"] == "in"
    assert item["body"] == текст
    assert item["body_len"] == len(текст)
    assert item["body_truncated"] is False
    assert item["reply_kind"] == "interested"


def test_очень_длинное_режется_явно(база):
    store, rid, *_ = база
    текст = "я" * (DIALOG_BODY_MAX + 5000)
    _входящее(store, rid, текст)
    (item,) = store.dialog_thread(rid)
    assert len(item["body"]) == DIALOG_BODY_MAX
    assert item["body_len"] == len(текст)          # честная исходная длина
    assert item["body_truncated"] is True          # а не молчаливый огрызок


# ---- симптом 2: наши письма с телом ------------------------------------- #

def test_живая_отправка_показывает_тело_из_решения(база):
    store, rid, cid, sid = база
    _наше_письмо(store, rid, cid, sid, body="Полный текст коммерческого")
    (item,) = store.dialog_thread(rid)
    assert item["direction"] == "out"
    # body_rendered в messages пуст — тело подтянуто из confirm_reviews
    assert store.get_message(item["message_id"]).body_rendered is None
    assert item["body"] == "Полный текст коммерческого"
    assert item["subject"] == "КП по компрессорам"


def test_правка_оператора_важнее_исходника(база):
    store, rid, cid, sid = база
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="k9", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=NOW))
    review_id, _ = store.confirm_submit(
        email="snab@zavod.ru", subject="Тема", body="сгенерированный текст",
        inn=ИНН, campaign_id=cid, recipient_id=rid, message_id=mid)
    store.confirm_decide(review_id, status="sent", edited_subject="Тема-правка",
                         edited_body="текст оператора", decided_by="owner")
    store.mark_sent(mid, "<k9@ru>", NOW)
    (item,) = store.dialog_thread(rid)
    assert item["body"] == "текст оператора"
    assert item["subject"] == "Тема-правка"


def test_наш_ответ_в_ветке_компании_с_телом(база):
    store, rid, *_ = база
    _входящее(store, rid, "Пришлите КП", ts=NOW - timedelta(hours=1))
    _наш_ответ(store, rid, body="Здравствуйте! Отправляю расчёт на 132 кВт.")
    ветка = store.dialog_thread_company(ИНН)
    исходящие = [i for i in ветка if i["direction"] == "out"]
    # ровно одна строка на ответ: раньше их было две — пустая из send_log
    # (subject «Re: Ваш запрос») и никакой с телом
    assert len(исходящие) == 1
    assert исходящие[0]["body"] == "Здравствуйте! Отправляю расчёт на 132 кВт."
    assert исходящие[0]["kind"] == "reply_sent"
    assert исходящие[0]["source"] == "confirm_reviews"
    assert исходящие[0]["email"] == "snab@zavod.ru"
    assert len(ветка) == 2


def test_письмо_кампании_не_двоится_с_журналом(база):
    store, rid, cid, sid = база
    _наше_письмо(store, rid, cid, sid, body="текст письма")
    ветка = store.dialog_thread_company(ИНН)
    assert len(ветка) == 1                       # messages ∪ send_log, не сумма
    assert ветка[0]["body"] == "текст письма"
    assert ветка[0]["source"] == "messages"


def test_два_ответа_в_тред_не_схлопываются(база):
    """Склейка send_log с решением оператора идёт 1:1 — два ответа с одной темой
    остаются двумя письмами, а не одним."""
    store, rid, *_ = база
    _наш_ответ(store, rid, body="первый ответ", ts=NOW - timedelta(hours=2),
               key="r1")
    _наш_ответ(store, rid, body="второй ответ", ts=NOW, key="r2")
    тела = [i["body"] for i in store.dialog_thread_company(ИНН)]
    assert sorted(тела) == ["второй ответ", "первый ответ"]


def test_касание_без_тела_помечено_явно(база):
    store, rid, *_ = база
    store.upsert_recipient(RecipientIn(
        email="old@zavod.ru", domain="zavod.ru", inn=ИНН, company_name="Завод"))
    store.send_log_add(email="old@zavod.ru", inn=ИНН,
                       ts=NOW - timedelta(days=200), subject="Старая рассылка")
    (item,) = store.dialog_thread_company(ИНН)
    assert item["body"] == ""
    assert item["body_missing"] is True           # «тела нет», а не пустота
    assert item["subject"] == "Старая рассылка"
    assert item["source"] == "send_log"


# ---- симптом 3: цепочка целиком ----------------------------------------- #

def test_хронология_по_возрастанию(база):
    store, rid, cid, sid = база
    _наше_письмо(store, rid, cid, sid, body="первое",
                 ts=NOW - timedelta(days=2), key="k1")
    _входящее(store, rid, "ответ клиента", ts=NOW - timedelta(days=1))
    _наш_ответ(store, rid, body="наш ответ", ts=NOW)
    ветка = store.dialog_thread_company(ИНН)
    assert [i["direction"] for i in ветка] == ["out", "in", "out"]
    assert [i["body"] for i in ветка] == ["первое", "ответ клиента", "наш ответ"]
    assert [i["ts"] for i in ветка] == sorted(i["ts"] for i in ветка)


def test_лимит_оставляет_свежие_письма(база):
    store, rid, cid, sid = база
    for n in range(5):
        _наше_письмо(store, rid, cid, sid, body=f"письмо {n}",
                     subject=f"Тема {n}", ts=NOW - timedelta(days=10 - n),
                     key=f"k{n}")
    ветка = store.dialog_thread_company(ИНН, limit=2)
    # раньше items[:limit] отдавал САМОЕ СТАРОЕ — оператор отвечал, не видя
    # последних писем
    assert [i["body"] for i in ветка] == ["письмо 3", "письмо 4"]


def test_пустой_инн_даёт_пустую_ветку(store):
    assert store.dialog_thread_company("") == []
    assert store.dialog_thread_company(None) == []


# ---- маршрут очереди: ветка подшивается и есть откат на контакт ---------- #

def _клиент(dialog_company, dialog_recipient):
    import inspect
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from sender.api.app import make_app, Principal

    строки = [{"id": 1, "email": "a@zavod.ru", "inn": "7701234567",
               "kind": "reply", "recipient_id": 5, "panel": {}}]

    class _Confirm:
        live = False

        def pending(self, **kw):
            return [dict(r) for r in строки]

        def counts(self):
            return {"pending": 1}

        def send_as(self, r):
            return {"mailbox_id": None, "options": [], "from_name": ""}

    class _Auth:
        def resolve(self, t):
            f = list(inspect.signature(Principal).parameters)
            v = {"user_id": 1, "username": "t", "role": "owner", "id": 1,
                 "is_active": True, "session_id": 1, "token": "x"}
            return Principal(**{k: v.get(k, "owner") for k in f})

    deps = SimpleNamespace(
        confirm=_Confirm(), auth=_Auth(), config=SimpleNamespace(),
        store=SimpleNamespace(
            sent_flags=lambda **kw: {}, get_campaign=lambda cid: None,
            dialog_thread_company=dialog_company,
            dialog_thread=dialog_recipient))
    return TestClient(make_app(deps), raise_server_exceptions=False)


def test_маршрут_подшивает_ветку_с_полным_телом():
    длинное = "текст письма " * 500
    c = _клиент(lambda inn, limit=60: [
        {"direction": "in", "ts": "2026-07-27T10:00:00.000000", "kind": "reply",
         "subject": "Re: КП", "body": длинное, "body_len": len(длинное),
         "body_truncated": False, "mailbox_id": "box1@ru"}],
        lambda rid, limit=60: [])
    got = c.get("/confirm/queue", headers={"Authorization": "Bearer x"})
    assert got.status_code == 200
    ветка = got.json()["pending"][0]["thread"]
    assert ветка[0]["body"] == длинное          # ничего не режется по дороге


def test_маршрут_откатывается_на_ветку_контакта():
    """Пустая ветка по ИНН больше не оставляет оператора без истории."""
    c = _клиент(lambda inn, limit=60: [],
                lambda rid, limit=60: [
                    {"direction": "in", "ts": "2026-07-27T10:00:00.000000",
                     "kind": "reply", "subject": "Re: КП", "body": "текст",
                     "mailbox_id": ""}])
    got = c.get("/confirm/queue", headers={"Authorization": "Bearer x"})
    assert got.status_code == 200
    ветка = got.json()["pending"][0]["thread"]
    assert len(ветка) == 1 and ветка[0]["body"] == "текст"
