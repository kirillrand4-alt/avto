"""Отбивка почтового сервера — не переписка с компанией.

Случай владельца 28.08.2026, ООО «ИМПЭКС-ДОН»: 24.08 письмо ушло на
info@impeks-don.ru, mail.ru ответил «550 invalid mailbox… user not found»;
28.08 письмо на mail@impeks-don.ru дошло, и человек ответил живым текстом с
телефоном зама. Оба адреса — одна компания, поэтому лента компании показала их
одной хронологией, и рядом с настоящим ответом висело «Ваше сообщение не
доставлено». Карточку лида владелец пересылает в отдел продаж — «они нифига не
поймут».

Проверяем ровно границу: из ленты КОМПАНИИ уведомления серверов уходят, из
технической ленты КОНТАКТА и из журнала событий (гейты, kill-switch считают
event_type='bounce') они не уходят никуда.
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
from sender.store import Store  # noqa: E402

UTC = timezone.utc
NOW = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=1)
ИНН = "6167128827"
МЁРТВЫЙ = "info@impeks-don.ru"
ЖИВОЙ = "mail@impeks-don.ru"
ОТБИВКА = ("Это письмо создано автоматически сервером Mail.ru.\n"
           "  info@impeks-don.ru\n"
           "    550 Message was not accepted -- invalid mailbox.")
ОТВЕТ = ("Добрый день, тема очень актуальная по стационарным компрессорам, "
         "данной темой занимается мой зам Поляков Виталий Валерьевич")


@pytest.fixture
def база(tmp_path):
    """Компания с двумя контактами: по мёртвому — отбивка, по живому — ответ."""
    store = Store(str(tmp_path / "otbivka.db"))
    store.init_schema()
    мёртвый = store.upsert_recipient(RecipientIn(
        email=МЁРТВЫЙ, domain="impeks-don.ru", inn=ИНН,
        company_name='ООО "ИМПЭКС-ДОН"'))
    живой = store.upsert_recipient(RecipientIn(
        email=ЖИВОЙ, domain="impeks-don.ru", inn=ИНН,
        company_name='ООО "ИМПЭКС-ДОН"'))
    cid = store.create_campaign(CampaignIn(
        name="КЦ", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    for адрес, rid, ключ, когда in ((МЁРТВЫЙ, мёртвый, "m1", NOW - timedelta(days=4)),
                                    (ЖИВОЙ, живой, "m2", NOW)):
        mid, _ = store.enqueue_message(MessageIn(
            idempotency_key=ключ, campaign_id=cid, recipient_id=rid,
            sequence_step_id=sid, scheduled_at=когда))
        store.mark_sent(mid, "<%s@ru>" % ключ, когда, mailbox_id="box1@ru")
        store.send_log_add(email=адрес, inn=ИНН, ts=когда, message_id=mid,
                           rfc_message_id="<%s@ru>" % ключ,
                           subject="Вопрос по компрессорам")
    store.append_event(EventIn(
        dedup_key="imap:1:11:dsn", event_type="bounce",
        event_ts=NOW - timedelta(days=4), recipient_id=мёртвый,
        mailbox_id="box1@ru",
        detail={"kind": "dsn", "snippet": ОТБИВКА,
                "headers": {"Subject": "Ваше сообщение не доставлено"}}))
    store.append_event(EventIn(
        dedup_key="imap:1:12:reply", event_type="reply", event_ts=NOW,
        recipient_id=живой, mailbox_id="box1@ru",
        detail={"snippet": ОТВЕТ, "headers": {"Subject": "Re: Вопрос"}}))
    yield store, мёртвый, живой
    store.close()


def test_v_lente_kompanii_otbivki_net(база):
    store, _, _ = база
    лента = store.dialog_thread_company(ИНН)
    входящие = [i for i in лента if i["direction"] == "in"]
    assert [i["kind"] for i in входящие] == ["reply"]
    assert ОТВЕТ in входящие[0]["body"]
    assert not any("не доставлено" in str(i.get("subject") or "") for i in лента)
    assert not any("invalid mailbox" in str(i.get("body") or "") for i in лента)


def test_pismo_kotoroe_ne_doshlo_tozhe_uhodit(база):
    """Письмо на мёртвый адрес — не «мы написали». Показать его без отбивки
    хуже, чем не показать вовсе: продажник читает это как «нам не ответили»."""
    store, _, _ = база
    лента = store.dialog_thread_company(ИНН)
    assert {i.get("email") for i in лента} == {ЖИВОЙ}
    assert len(лента) == 2                       # наше письмо и ответ на него


def test_snyatoe_pismo_ne_vozvrashchaetsya_iz_zhurnala(база):
    """send_log и решения оператора — отдельные источники ленты; снятый адрес
    возвращался оттуда строкой без тела."""
    store, _, _ = база
    assert not [i for i in store.dialog_thread_company(ИНН)
                if i.get("body_missing")]


def test_esli_otvetili_pisma_ostayutsya(база):
    """Мягкая отбивка, а потом человек ответил — переписка была, и она нужна
    целиком; уходит только само уведомление сервера."""
    store, мёртвый, _ = база
    store.append_event(EventIn(
        dedup_key="imap:1:13:reply", event_type="reply",
        event_ts=NOW + timedelta(minutes=5), recipient_id=мёртвый,
        mailbox_id="box1@ru",
        detail={"snippet": "Письмо дошло со второго раза, давайте обсудим",
                "headers": {"Subject": "Re: Вопрос"}}))
    адреса = {i.get("email") for i in store.dialog_thread_company(ИНН)}
    assert адреса == {МЁРТВЫЙ, ЖИВОЙ}
    assert not any(i.get("kind") == "bounce"
                   for i in store.dialog_thread_company(ИНН))


def test_polnaya_lenta_po_zaprosu(база):
    """Техническому потребителю отбивка доступна — просто не по умолчанию."""
    store, _, _ = база
    лента = store.dialog_thread_company(ИНН, bez_otbivok=False)
    assert any(i.get("kind") == "bounce" for i in лента)


def test_lenta_kontakta_ne_tronuta(база):
    """dialog_thread — техническая карточка контакта, там отбивка нужна."""
    store, мёртвый, _ = база
    виды = [i["kind"] for i in store.dialog_thread(мёртвый)]
    assert "bounce" in виды


def test_sobytie_v_zhurnale_ostalos(база):
    """Гейты и kill-switch считают event_type='bounce' — счётчик не трогаем."""
    store, _, _ = база
    assert store.count_events(event_type="bounce") == 1
