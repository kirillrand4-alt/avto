# -*- coding: utf-8 -*-
"""Домен без почтового сервера: приговор только после второй проверки.

Владелец 12.08: «мы иногда отправляем письма сразу, проверь сам ещё раз и сними
сразу». Отсутствие MX означает, что письмо физически некуда доставить, и такое
письмо разумно снимать наравне с «нет такого пользователя». Но одного пустого
ответа DNS мало: резолвер сбоит, ответ срезается, а выброшенный домен назад не
вернёшь. Поэтому спрашиваем тремя путями и хороним, только когда пусто везде.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from sender.addr_probe import НЕТ_MX, НЕЯСНО, AddrProbe  # noqa: E402


@pytest.fixture
def проба():
    p = AddrProbe.__new__(AddrProbe)
    return p


def _подменить(monkeypatch, проба, *, dnspython=None, nslookup=None, a_zapis=False):
    """dnspython/nslookup: 'нашёл' | 'пусто' | 'молчит'."""
    class _Ответ:
        def __init__(self, есть):
            self._есть = есть

        def __iter__(self):
            return iter([object()] if self._есть else [])

    class _Резолвер:
        @staticmethod
        def resolve(*_a, **_k):
            if dnspython == "нашёл":
                return _Ответ(True)
            if dnspython == "пусто":
                raise Exception("NoAnswer: The DNS response does not contain")
            raise Exception("Timeout: The DNS operation timed out")

    import types
    модуль = types.ModuleType("dns")
    модуль.resolver = _Резолвер
    monkeypatch.setitem(sys.modules, "dns", модуль)
    monkeypatch.setitem(sys.modules, "dns.resolver", _Резолвер)

    class _Готово:
        stdout = ("mail exchanger = mx.example.ru" if nslookup == "нашёл"
                  else ("connection timed out; no servers could be reached"
                        if nslookup == "молчит" else "*** No MX records"))

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Готово())

    def _host(*_a, **_k):
        if a_zapis:
            return "1.2.3.4"
        raise OSError("no A record")

    monkeypatch.setattr("socket.gethostbyname", _host)


def test_oba_rezolvera_pusto_eto_prigovor(monkeypatch, проба):
    _подменить(monkeypatch, проба, dnspython="пусто", nslookup="пусто")
    приговор, почему = проба._net_mx_dvazhdy("mertvyy.ru")
    assert приговор is True, почему


def test_dnspython_nashyol_mx_ne_prigovor(monkeypatch, проба):
    _подменить(monkeypatch, проба, dnspython="нашёл", nslookup="пусто")
    приговор, почему = проба._net_mx_dvazhdy("zhivoy.ru")
    assert приговор is False and "нашёл MX" in почему


def test_sistemnyy_rezolver_nashyol_mx_ne_prigovor(monkeypatch, проба):
    _подменить(monkeypatch, проба, dnspython="пусто", nslookup="нашёл")
    приговор, почему = проба._net_mx_dvazhdy("zhivoy2.ru")
    assert приговор is False and "системный резолвер" in почему


def test_a_zapis_spasaet_domen(monkeypatch, проба):
    """По RFC 5321 почту можно слать на A-адрес, если MX нет вовсе."""
    _подменить(monkeypatch, проба, dnspython="пусто", nslookup="пусто",
               a_zapis=True)
    приговор, почему = проба._net_mx_dvazhdy("tolko-a.ru")
    assert приговор is False and "по A" in почему


def test_molchanie_rezolvera_ne_prigovor(monkeypatch, проба):
    """Молчание — это про сеть, а не про домен: хоронить нельзя."""
    _подменить(monkeypatch, проба, dnspython="молчит", nslookup="молчит")
    приговор, почему = проба._net_mx_dvazhdy("neyasno.ru")
    assert приговор is False, почему


def test_odin_otvetil_pusto_drugoy_molchit_ne_prigovor(monkeypatch, проба):
    """Одного «пусто» мало — нужны оба."""
    _подменить(monkeypatch, проба, dnspython="пусто", nslookup="молчит")
    приговор, _ = проба._net_mx_dvazhdy("polovina.ru")
    assert приговор is False


def test_snyat_pismo_i_pohoronit_adres_raznye_veshchi():
    """Снятие письма и похороны адреса — разные списки вердиктов.

    До 24.08 это было одно и то же: снимали письмо ровно там, где хоронили
    адрес, и «неясно» не делало ни того, ни другого. Владелец 24.08 развёл
    их: «проба не смогла добиться ответа = вот такие надо убирать из очереди
    отправок». Письмо по «неясно» снимается, адрес — нет: молчание чужого
    почтовика не повод закрыть живой контакт навсегда, а снятую карточку
    генерация принесёт заново.

    Проверяем сами списки, а не текст исходника: прежний вариант этого теста
    искал строку "in (НЕТ_ЯЩИКА, НЕТ_MX)" внутри tick и падал от любой
    законной правки, ничего не говоря о поведении.
    """
    from sender.addr_probe import (НЕТ_ЯЩИКА, ПОХОРОНИТЬ_АДРЕС,
                                   СНЯТЬ_С_ОЧЕРЕДИ)

    assert set(ПОХОРОНИТЬ_АДРЕС) == {НЕТ_ЯЩИКА, НЕТ_MX}
    assert НЕЯСНО in СНЯТЬ_С_ОЧЕРЕДИ
    assert НЕЯСНО not in ПОХОРОНИТЬ_АДРЕС
    assert set(ПОХОРОНИТЬ_АДРЕС) <= set(СНЯТЬ_С_ОЧЕРЕДИ)


# --- заслон на подтверждении ------------------------------------------------ #

class _ПробаЗаглушка:
    """Кэш вердиктов без сети."""

    def __init__(self, вердикты=None, приговор_домену=False):
        self._в = вердикты or {}
        self._приговор = приговор_домену
        self.спрошено = []

    def cached(self, адрес):
        return self._в.get(адрес.lower())

    def _net_mx_dvazhdy(self, домен):
        self.спрошено.append(домен)
        return (self._приговор, "заглушка")


def _confirm(проба):
    from sender.confirm import ConfirmSend
    c = ConfirmSend.__new__(ConfirmSend)
    c._probe = проба
    return c


def test_zaslon_ne_puskaet_nesushchestvuyushchiy_yashchik():
    from sender.addr_probe import НЕТ_ЯЩИКА

    п = _ПробаЗаглушка({"a@b.ru": {"verdict": НЕТ_ЯЩИКА, "answer": "no such user"}})
    причина = _confirm(п)._nedostavimyy("a@b.ru")
    assert причина and "не существует" in причина


def test_zaslon_ne_puskaet_domen_bez_pochty():
    п = _ПробаЗаглушка({"a@b.ru": {"verdict": НЕТ_MX}})
    причина = _confirm(п)._nedostavimyy("a@b.ru")
    assert причина and "почтового сервера" in причина


def test_zhivoy_adres_prohodit():
    п = _ПробаЗаглушка({"a@b.ru": {"verdict": "есть"}})
    assert _confirm(п)._nedostavimyy("a@b.ru") is None


def test_bez_verdikta_sprashivaem_tolko_domen():
    """Живой SMTP-пробы здесь быть не должно: она тратит репутацию боевого IP.
    Спрашиваем только DNS о почтовом сервере домена."""
    п = _ПробаЗаглушка({}, приговор_домену=True)
    причина = _confirm(п)._nedostavimyy("kto@nomx.ru")
    assert причина and "почтового сервера" in причина
    assert п.спрошено == ["nomx.ru"]


def test_bez_verdikta_i_zhivoy_domen_prohodit():
    п = _ПробаЗаглушка({}, приговор_домену=False)
    assert _confirm(п)._nedostavimyy("kto@zhivoy.ru") is None


def test_bez_proby_zaslon_molchit():
    """Инструменты и тесты собирают ConfirmSend без пробы — отправку не рвём."""
    assert _confirm(None)._nedostavimyy("a@b.ru") is None
