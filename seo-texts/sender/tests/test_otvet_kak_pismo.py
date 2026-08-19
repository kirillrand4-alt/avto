"""Ответ оператора должен оставлять строку письма (владелец 19.08).

«Оператор ответила на письмо, но нигде нету информации об этом». Ответ
уходил по-настоящему — send_log и событие reply_sent, — но строки в
messages не заводил, и потому не появлялся ни в «Отправленных», ни в
статистике ящика; событие приходило с message_id=None.

Проверяю поведение store.otvet_kak_pismo:
  * строка заводится со статусом sent, темой, телом и привязкой к треду;
  * повторный вызов на том же rfc_message_id не плодит вторую;
  * без прошлого письма получателю строка не заводится (кампанию и шаг
    брать неоткуда, колонки NOT NULL) — и это не ошибка, а честный отказ.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.dtos import (CampaignIn, MessageIn, RecipientIn,  # noqa: E402
                         SequenceStepIn)
from sender.store import Store  # noqa: E402


def _база(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.init_schema()
    cid = store.create_campaign(CampaignIn(
        name="проба", legal_entity="ООО Руспром", legal_inn="2221239841"))
    step_id = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="тема", body_tmpl="тело"))
    rid = store.upsert_recipient(RecipientIn(
        email="klient@firma.ru", domain="firma.ru", inn="7700000001",
        company_name="ООО Тест"))
    return store, cid, step_id, rid


def _исходное(store, cid, step_id, rid):
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=int(step_id),
        scheduled_at=datetime.now(timezone.utc)))
    store.mark_sent(mid, "<orig@mail>", datetime.now(timezone.utc),
                    mailbox_id="box1")
    return mid


def test_otvet_zavodit_stroku(tmp_path):
    store, cid, step_id, rid = _база(tmp_path)
    _исходное(store, cid, step_id, rid)
    mid = store.otvet_kak_pismo(
        recipient_id=rid, mailbox_id="box1", subject="Re: тема",
        body="текст ответа", rfc_message_id="<reply1@mail>",
        sent_at=datetime.now(timezone.utc), in_reply_to="<orig@mail>",
        thread_id="t1")
    assert mid
    with store._lock:
        r = store._conn.execute(
            "SELECT status, subject, body_rendered, in_reply_to, mailbox_id "
            "FROM messages WHERE id=?", (mid,)).fetchone()
    assert r["status"] == "sent"
    assert r["subject"] == "Re: тема"
    assert r["body_rendered"] == "текст ответа"
    assert r["in_reply_to"] == "<orig@mail>"
    assert r["mailbox_id"] == "box1"


def test_povtor_ne_plodit_vtoruyu(tmp_path):
    store, cid, step_id, rid = _база(tmp_path)
    _исходное(store, cid, step_id, rid)
    общее = dict(recipient_id=rid, mailbox_id="box1", subject="Re: тема",
                 body="текст", rfc_message_id="<reply1@mail>",
                 sent_at=datetime.now(timezone.utc))
    первый = store.otvet_kak_pismo(**общее)
    второй = store.otvet_kak_pismo(**общее)
    assert первый == второй
    with store._lock:
        n = store._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE rfc_message_id=?",
            ("<reply1@mail>",)).fetchone()[0]
    assert n == 1


def test_bez_proshlogo_pisma_ne_zavodit(tmp_path):
    """Компании, которой мы не писали, кампанию и шаг взять неоткуда."""
    store, cid, step_id, rid = _база(tmp_path)
    assert store.otvet_kak_pismo(
        recipient_id=rid, mailbox_id="box1", subject="Re: тема",
        body="текст", rfc_message_id="<reply2@mail>",
        sent_at=datetime.now(timezone.utc)) is None
