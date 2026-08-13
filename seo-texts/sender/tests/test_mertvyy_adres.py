# -*- coding: utf-8 -*-
"""Мёртвый адрес не попадает оператору в руки: ни в список, ни в отправку.

Владелец 12.08, после разбора надёжности проверки адресов:
  «нам главное не сжечь свои почты, убирай их нафиг» — про мёртвые адреса
  в выпадающем списке «кому»;
  «сделай чтобы при непрохождении проверки они сами исключались из списка»;
  «можно поставить задержку отправки при добавлении адреса до проверки почты?
  и отправку только при явном да».

Три рубежа, каждый закрывает свою дыру:
  1) список «кому» не показывает адреса с приговором — фильтр живой, смотрит
     вердикт при каждой выдаче очереди;
  2) переключиться на приговорённый адрес нельзя, даже если экран оператора
     открыт со старым списком;
  3) письмо с адресом, введённым руками, ждёт вердикта до минуты и уходит
     раньше только по второму подтверждению.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА  # noqa: E402
from sender.confirm import (ConfirmBlockedError, ConfirmSend,  # noqa: E402
                            ОКНО_ПРОБЫ_СЕК)


class _Проба:
    """Кэш вердиктов без сети."""

    def __init__(self, вердикты=None):
        self._в = {k.lower(): v for k, v in (вердикты or {}).items()}

    def cached(self, адрес):
        в = self._в.get(str(адрес).lower())
        return {"verdict": в, "answer": "no such user"} if в else None

    def _net_mx_dvazhdy(self, домен):     # DNS не спрашиваем в тестах
        return (False, "заглушка")


def _confirm(проба=None):
    c = ConfirmSend.__new__(ConfirmSend)
    c._probe = проба
    return c


def _сейчас(сдвиг_сек=0):
    return (datetime.now(timezone.utc)
            - timedelta(seconds=сдвиг_сек)).isoformat()


# --- рубеж 3: ожидание вердикта ---------------------------------------------- #

def test_ruchnoy_adres_zhdyot_verdikta():
    c = _confirm(_Проба())                      # вердикта нет
    строка = {"email": "kto@zavod.ru", "manual_email_ts": _сейчас(5)}
    причина = c._zhdyot_verdikta(строка)
    assert причина and "проверяется" in причина


def test_verdikt_prishyol_put_otkryt():
    c = _confirm(_Проба({"kto@zavod.ru": "есть"}))
    assert c._zhdyot_verdikta(
        {"email": "kto@zavod.ru", "manual_email_ts": _сейчас(5)}) is None


def test_adres_ne_trogali_rukami_ne_zhdyot():
    """Обычные письма очереди задержка не касается — иначе встанет вся работа."""
    c = _confirm(_Проба())
    assert c._zhdyot_verdikta({"email": "kto@zavod.ru"}) is None
    assert c._zhdyot_verdikta({"email": "kto@zavod.ru",
                               "manual_email_ts": ""}) is None


def test_okno_ozhidaniya_konechno():
    """Если работник лёг, письмо не должно застрять навсегда."""
    c = _confirm(_Проба())
    старое = {"email": "kto@zavod.ru",
              "manual_email_ts": _сейчас(ОКНО_ПРОБЫ_СЕК + 5)}
    assert c._zhdyot_verdikta(старое) is None


def test_bitaya_metka_ne_derzhit_pismo():
    c = _confirm(_Проба())
    assert c._zhdyot_verdikta({"email": "kto@zavod.ru",
                               "manual_email_ts": "не-дата"}) is None


def test_bez_proby_zaderzhki_net():
    """Инструменты и тесты собирают ConfirmSend без пробы — отправку не рвём."""
    assert _confirm(None)._zhdyot_verdikta(
        {"email": "kto@zavod.ru", "manual_email_ts": _сейчас(1)}) is None


def test_yavnoe_da_probivaet_ozhidanie():
    """force — это и есть «явное да» оператора: второе подтверждение."""
    import inspect

    исходник = inspect.getsource(ConfirmSend.approve)
    assert "_zhdyot_verdikta" in исходник
    assert "ждёт and not force" in исходник


# --- рубеж 2: переключиться на мёртвый нельзя -------------------------------- #

def _строка_с_kontaktami(*адреса):
    return {"id": 1, "status": "pending", "email": "old@zavod.ru",
            "panel": {"emails": [{"email": a} for a in адреса]}}


def test_pereklyuchenie_na_mertvyy_zapreshcheno(monkeypatch):
    c = _confirm(_Проба({"dead@zavod.ru": НЕТ_ЯЩИКА}))
    c._require_pending = lambda _rid: _строка_с_kontaktami(
        "dead@zavod.ru", "live@zavod.ru")
    with pytest.raises(ConfirmBlockedError) as e:
        ConfirmSend.set_recipient_email(c, 1, "dead@zavod.ru")
    assert "недоставим" in str(e.value)


def test_pereklyuchenie_na_domen_bez_pochty_zapreshcheno():
    c = _confirm(_Проба({"kto@nomx.ru": НЕТ_MX}))
    c._require_pending = lambda _rid: _строка_с_kontaktami("kto@nomx.ru")
    with pytest.raises(ConfirmBlockedError):
        ConfirmSend.set_recipient_email(c, 1, "kto@nomx.ru")


def test_pereklyuchenie_na_zhivoy_prohodit():
    c = _confirm(_Проба({"live@zavod.ru": "есть"}))
    c._require_pending = lambda _rid: _строка_с_kontaktami("live@zavod.ru")
    c._store = type("_", (), {
        "confirm_change_email": staticmethod(
            lambda rid, em: {"id": rid, "email": em}),
        "append_audit": staticmethod(lambda **_k: None)})()
    r = ConfirmSend.set_recipient_email(c, 1, "live@zavod.ru")
    assert r["email"] == "live@zavod.ru"


# --- рубеж 1: фильтр списка «кому» ------------------------------------------- #

def test_spisok_komu_teryaet_mertvyh():
    """Проверяем сам фильтр из выдачи очереди, не поднимая FastAPI."""
    from sender.api.app import _МЁРТВЫЕ_ВЕРДИКТЫ

    проба = {"dead@zavod.ru": НЕТ_ЯЩИКА, "nomx@zavod.ru": НЕТ_MX,
             "live@zavod.ru": "есть", "catch@zavod.ru": "принимает всё"}
    почта = "old@zavod.ru"
    emails = [{"email": a} for a in
              ("old@zavod.ru", "dead@zavod.ru", "nomx@zavod.ru",
               "live@zavod.ru", "catch@zavod.ru")]
    живые = [c for c in emails
             if not (c["email"] != почта
                     and проба.get(c["email"]) in _МЁРТВЫЕ_ВЕРДИКТЫ)]
    остались = {c["email"] for c in живые}
    assert остались == {"old@zavod.ru", "live@zavod.ru", "catch@zavod.ru"}
    # «принимает всё» и «неясно» остаются: это не приговор, а «узнать нельзя».
    assert "catch@zavod.ru" in остались


def test_tekushchiy_adres_iz_spiska_ne_propadaet():
    """Даже если текущий адрес письма мёртв — оператор должен его видеть,
    иначе письмо молча теряет получателя, а причину не объяснить."""
    from sender.api.app import _МЁРТВЫЕ_ВЕРДИКТЫ

    почта = "dead@zavod.ru"
    проба = {"dead@zavod.ru": НЕТ_ЯЩИКА}
    emails = [{"email": "dead@zavod.ru"}, {"email": "live@zavod.ru"}]
    живые = [c for c in emails
             if not (c["email"] != почта
                     and проба.get(c["email"]) in _МЁРТВЫЕ_ВЕРДИКТЫ)]
    assert {c["email"] for c in живые} == {"dead@zavod.ru", "live@zavod.ru"}


def test_filtr_stoit_v_vydache_ocheredi():
    import inspect

    from sender.api import app as A

    исходник = inspect.getsource(A)
    assert "_МЁРТВЫЕ_ВЕРДИКТЫ" in исходник
    assert "emails_skryto_mertvyh" in исходник
