# -*- coding: utf-8 -*-
"""Повторное письмо оживляет снятую карточку, а не пропадает.

СЛУЧАЙ 25.08.2026. Компании вернулись в пул генерации, им написали новые
письма, а очередь отдала те же СНЯТЫЕ карточки и по «ON CONFLICT DO
NOTHING» ничего в них не записала. 632 оплаченных письма легли в никуда:
оператор их не видел, а генератор считал постановку удачной, потому что
ConfirmSend.submit возвращал жёсткое "pending" вместо статуса из базы.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.dtos import CampaignIn, RecipientIn, SequenceStepIn  # noqa: E402
from sender.store import Store  # noqa: E402


def _стор():
    s = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
    s.init_schema()
    return s


def _положить(s, **правки):
    поля = dict(email="kto@zavod.ru", subject="Тема", body="Тело",
                inn="7700000000", campaign_id=None, recipient_id=None)
    поля.update(правки)
    return s.confirm_submit(**поля)


def test_pervoe_pismo_zavodit_kartochku():
    s = _стор()
    rid, created = _положить(s)
    assert created is True
    assert s.confirm_get(rid)["status"] == "pending"


def test_povtor_v_pending_nichego_ne_lomaet():
    """У живой карточки своя жизнь: оператор мог её править."""
    s = _стор()
    rid, _ = _положить(s)
    rid2, created = _положить(s, subject="Другая", body="Другое")
    assert rid2 == rid and created is False
    к = s.confirm_get(rid)
    assert к["status"] == "pending"
    assert к["subject"] == "Тема", "живую карточку не перетираем"


def test_snyatuyu_kartochku_ozhivlyaem_novym_pismom():
    s = _стор()
    rid, _ = _положить(s)
    s.confirm_decide(rid, status="skipped", decided_by="тест",
                     reason="механическая сборка")
    assert s.confirm_get(rid)["status"] == "skipped"

    rid2, created = _положить(s, subject="Свежая тема", body="Свежее тело")
    assert rid2 == rid and created is False
    к = s.confirm_get(rid)
    assert к["status"] == "pending", "снятая карточка обязана ожить"
    assert к["subject"] == "Свежая тема"
    assert к["body"] == "Свежее тело"


def test_vmeste_s_kartochkoy_podnimaetsya_pismo():
    """Оживить карточку мало: письмо осталось бы снятым, и автоотправка его
    не увидит — оператор подтвердит то, что никуда не уйдёт."""
    s = _стор()
    cid = s.create_campaign(CampaignIn(name="к", legal_entity="ООО Руспром",
                                       legal_inn="2221239841"))
    sid = s.add_step(SequenceStepIn(campaign_id=cid, step_index=1,
                                    delay_hours=0, subject_tmpl="т",
                                    body_tmpl="б"))
    rid_p = s.upsert_recipient(RecipientIn(email="kto@zavod.ru",
                                          domain="zavod.ru"))
    with s.transaction() as conn:
        conn.execute(
            "INSERT INTO messages(idempotency_key, campaign_id, recipient_id, "
            "  sequence_step_id, status, created_at, updated_at) "
            "VALUES('k1',?,?,?,'skipped','2026-08-25','2026-08-25')",
            (cid, rid_p, sid))
        mid = conn.execute("SELECT id FROM messages").fetchone()["id"]

    rid, _ = _положить(s, message_id=mid, campaign_id=cid, recipient_id=rid_p)
    s.confirm_decide(rid, status="skipped", decided_by="тест",
                     reason="механическая сборка")
    _положить(s, message_id=mid, campaign_id=cid, recipient_id=rid_p,
              subject="Свежая", body="Свежее")
    with s.transaction() as conn:
        ст = conn.execute("SELECT status FROM messages WHERE id=?",
                          (mid,)).fetchone()["status"]
    assert s.confirm_get(rid)["status"] == "pending"
    assert ст == "pending_review", "письмо обязано подняться вместе с карточкой"


def test_otpravlennuyu_ne_trogaem():
    """Письмо уже ушло — перетирать его текст нельзя ни при каких условиях."""
    s = _стор()
    rid, _ = _положить(s)
    s.confirm_decide(rid, status="sent", decided_by="тест", reason="ушло")
    _положить(s, subject="Свежая", body="Свежее")
    к = s.confirm_get(rid)
    assert к["status"] == "sent"
    assert к["subject"] == "Тема"
