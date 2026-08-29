"""Ответ новым письмом — тоже ответ, а стоп-лист спрашивают до генерации.

29.08, две находки одного разбора ленты:

  * половина деловой почты отвечает НЕ «ответить», а новым письмом с новой
    темой: «компрессор КИП.», «Ооо ТЭКО», «Доброе утро! Вопрос компрессорного
    оборудования…». Ответом считалось только письмо с In-Reply-To/References,
    поэтому такие ложились «входящим вне переписки»: ни ответа в сводке, ни
    карточки лида. Из 253 записей «вне переписки» 23 оказались письмами живых
    людей, 11 из них — привязанными к компании;

  * письма генерировались на адреса из стоп-листа: 277 черновиков, у 256
    запись в стоп-листе появилась РАНЬШЕ письма. Отбор просил
    query_recipients({'suppressed': False}) — а это ФЛАГ в карточке, который
    отстаёт от таблицы suppression.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.ai_quota import AiQuota  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MessageIn, RecipientIn, SequenceStepIn, SuppressionIn,
)
from sender.imap_watcher import ImapWatcher  # noqa: E402
from sender.store import Store  # noqa: E402

UTC = timezone.utc


# ---- машинный отправитель ------------------------------------------------- #

@pytest.mark.parametrize("адрес", [
    "noreply@id.yandex.ru", "no-reply@bgsp.bitrix24.ru",
    "MAILER-DAEMON@mail.ru", "postmaster@corp.ru", "notification@bank.ru",
    "MDaemon@udmgas.udm.ru"])
def test_mashinu_uznayom(адрес):
    assert ImapWatcher._ot_mashiny(адрес) is True


@pytest.mark.parametrize("адрес", [
    "vasileav@cryo-gas.ru", "gi@okbexiton.ru", "slobvod@mail.ru",
    "s9213674759@gmail.com"])
def test_cheloveka_ne_putaem_s_mashinoy(адрес):
    assert ImapWatcher._ot_mashiny(адрес) is False


# ---- «писали ли раньше» --------------------------------------------------- #

@pytest.fixture
def база(tmp_path):
    store = Store(str(tmp_path / "otvet.db"))
    store.init_schema()
    rid = store.upsert_recipient(RecipientIn(
        email="snab@zavod.ru", domain="zavod.ru", inn="7701234567",
        company_name="Завод"))
    cid = store.create_campaign(CampaignIn(
        name="К1", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    yield store, rid, cid, sid
    store.close()


def _kvota(store):
    к = AiQuota.__new__(AiQuota)
    к._db_path = store._db_path                        # noqa: SLF001
    return к


def _watcher(store):
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = store
    return w


def test_bez_nashego_pisma_ne_otvet(база):
    """Рассылка компании, которой мы не писали, ответом быть не должна."""
    store, rid, _, _ = база
    assert _watcher(store)._pisali_ranshe(rid) is False


def test_posle_nashego_pisma_otvet(база):
    store, rid, cid, sid = база
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="k1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    store.mark_sent(mid, "<k1@ru>", datetime.now(UTC), mailbox_id="box1@ru")
    assert _watcher(store)._pisali_ranshe(rid) is True


def test_sboy_ne_ronyaet_priyom():
    """Сломанное хранилище не должно ронять приём письма — только вернуть
    «не писали»: лучше недосчитать ответ, чем потерять письмо целиком."""
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = object()
    assert w._pisali_ranshe(1) is False


# ---- стоп-лист до генерации ----------------------------------------------- #

def test_otbor_ne_beryot_adres_iz_stop_lista(база):
    store, rid, cid, _ = база
    store.suppression_add(SuppressionIn(
        scope="email", value="snab@zavod.ru", reason="bounce_hard",
        source="test"))
    assert _kvota(store)._v_stop_liste([store.get_recipient(rid)]) == {rid}


def test_chistyy_adres_prohodit(база):
    store, rid, _, _ = база
    assert _kvota(store)._v_stop_liste([store.get_recipient(rid)]) == set()


def test_stop_po_innu_tozhe_lovim(база):
    """Запрет ставят и на компанию целиком — «сделка уже в работе»."""
    store, rid, _, _ = база
    store.suppression_add(SuppressionIn(
        scope="inn", value="7701234567", reason="deal_in_progress",
        source="test"))
    assert _kvota(store)._v_stop_liste([store.get_recipient(rid)]) == {rid}
