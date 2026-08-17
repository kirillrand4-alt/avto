# -*- coding: utf-8 -*-
"""Стоп-лист держит вход в очередь подтверждений, а не только оркестратор.

Владелец 17.08 нашёл в очереди «Богатых карточек» пять компаний из
стоп-листа. Партию ставил серверный скрипт: он звал confirm_submit напрямую
и заслон, живший в оркестраторе, обошёл. Оператору предлагали подтвердить
живую отправку тому, кому слать нельзя, - включая компанию со сделкой в
работе.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.dtos import SuppressionIn                          # noqa: E402
from sender.store import Store                                 # noqa: E402


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


def _полож(store, **kw):
    return store.confirm_submit(
        subject="Тема", body="Тело", campaign_id=1, **kw)


class TestZaslonStopLista:
    def test_email_iz_stop_lista_ne_vstayot_v_ochered(self, store):
        store.suppression_add(SuppressionIn(
            scope="email", value="zakupki@stmost.ru", reason="bounce_hard"))
        rid, created = _полож(store, email="zakupki@stmost.ru")
        assert created
        строка = store.confirm_get(rid)
        assert строка["status"] == "skipped", строка
        assert "стоп-лист" in (строка["reason"] or ""), строка

    def test_inn_iz_stop_lista_lovitsya_pri_drugoy_pochte(self, store):
        # Именно так и прорвало: адреса разные, юрлицо одно.
        store.suppression_add(SuppressionIn(
            scope="inn", value="6230029069", reason="manual"))
        rid, _ = _полож(store, email="nkaravaeva@tochinvest.ru",
                        inn="6230029069")
        assert store.confirm_get(rid)["status"] == "skipped"

    def test_domen_iz_stop_lista(self, store):
        store.suppression_add(SuppressionIn(
            scope="domain", value="kip-group.com", reason="manual"))
        rid, _ = _полож(store, email="zakaz@kip-group.com")
        assert store.confirm_get(rid)["status"] == "skipped"

    def test_chistyy_poluchatel_prohodit(self, store):
        rid, _ = _полож(store, email="info@zavod.ru", inn="7701234567")
        строка = store.confirm_get(rid)
        assert строка["status"] == "pending", строка
        assert not (строка["reason"] or "")

    def test_otvet_v_trede_zaslonom_ne_rezhetsya(self, store):
        # kind='reply' - ответ человеку, который написал нам сам. Стоп-лист
        # холодных рассылок его не касается.
        store.suppression_add(SuppressionIn(
            scope="email", value="ivan@zavod.ru", reason="manual"))
        rid, _ = store.confirm_submit(
            subject="Re: вопрос", body="Тело", email="ivan@zavod.ru",
            kind="reply", dedup_key="tred-1")
        assert store.confirm_get(rid)["status"] == "pending"

    def test_yavnyy_skipped_ne_perebivaetsya(self, store):
        rid, _ = _полож(store, email="info@zavod.ru", status="skipped",
                        reason="своя причина")
        assert store.confirm_get(rid)["reason"] == "своя причина"
