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


def test_verdikty_snimayushchie_pismo():
    """Снимают письмо ровно два вердикта, и «неясно» среди них нет."""
    import inspect

    from sender import addr_probe as AP

    исходник = inspect.getsource(AP.AddrProbeLoop.tick)
    assert "in (НЕТ_ЯЩИКА, НЕТ_MX)" in исходник, исходник[:400]
    assert НЕЯСНО not in (НЕТ_MX,)
