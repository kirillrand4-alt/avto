# -*- coding: utf-8 -*-
"""Тумблер «слать вне базы» уважают ОБА слоя (13.08).

Жалоба редактора: «стопы всё время загораются». Замер на боевой базе: шесть
писем умерли причиной company_division_empty на этапе SMTP, все шесть — по
ИНН, которых нет в базе обзвона (новостные лиды), при этом тумблер
allow_out_of_base владелец включил ещё 07.08.

Расхождение слоёв: экран подтверждения тумблер читал (жёлтое предупреждение,
кнопка работает), рубеж перед SMTP — не читал вовсе и убивал письмо после
нажатия. Здесь фиксируем обе стороны и границу: настоящее расхождение
направлений тумблер НЕ снимает.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.errors import SuppressedError  # noqa: E402
from sender.tests.test_division_gate import (  # noqa: E402
    KC_INN, MEYER_INN, _rendered, _seed, _sender, cards, config, store,
)
from sender.vne_bazy import razreshena  # noqa: E402

UTC = timezone.utc
ВНЕ_БАЗЫ = "7700000000"     # ИНН не из базы обзвона

__all__ = ["cards", "config", "store"]  # фикстуры импортированы намеренно


# --- чтение тумблера ---------------------------------------------------------- #

class _Store:
    def __init__(self, значение):
        self._v = значение

    def get_setting(self, key, default=None):
        return self._v if key == "allow_out_of_base" else default


class _Cfg:
    def __init__(self, значение):
        self._v = значение

    def get(self, key, default=None):
        return self._v if key == "confirm.allow_out_of_base" else default


def test_tumbler_iz_paneli_glavnee_konfiga():
    assert razreshena(_Store(True), _Cfg(False)) is True
    assert razreshena(_Store(False), _Cfg(True)) is False


def test_bez_tumblera_beryotsya_konfig():
    assert razreshena(_Store(None), _Cfg(True)) is True
    assert razreshena(_Store(None), _Cfg(False)) is False


def test_po_umolchaniyu_vyklyucheno():
    assert razreshena(None, None) is False
    assert razreshena(object(), object()) is False


def test_stroka_false_ne_schitaetsya_vklyuchennym():
    """Настройка может приехать сырой строкой — 'false' это ВЫКЛ."""
    assert razreshena(_Store("false"), None) is False
    assert razreshena(_Store("true"), None) is True


# --- рубеж перед SMTP --------------------------------------------------------- #

def test_smtp_ubivaet_vne_bazy_pri_vyklyuchennom_tumblere(config, store, cards):
    _cid, _rid, mid = _seed(store, inn=ВНЕ_БАЗЫ)
    sndr = _sender(config, store, cards)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(store.get_message(mid), _rendered(), "box1@rusprom.ru",
                  now=datetime.now(UTC))
    assert store.get_message(mid).status == "skipped"


def test_smtp_propuskaet_vne_bazy_pri_vklyuchennom_tumblere(config, store, cards):
    """Тот самый случай редактора: тумблер ВКЛ — письмо обязано уйти.

    Время прибито намеренно. Соседние тесты файла падают на гейте направлений
    раньше окна отправки, а этот — единственный, кто доходит до пейсинга, и на
    живых часах он проходил только в будни с 9:30 до 18:00 МСК. Проверяем
    тумблер, а не время суток: среда, 12:00 МСК = 09:00 UTC.
    """
    store.set_setting("allow_out_of_base", True)
    _cid, _rid, mid = _seed(store, inn=ВНЕ_БАЗЫ)
    sndr = _sender(config, store, cards)
    sndr._deliver = lambda *a, **k: None      # сеть не нужна: проверяем гейт
    res = sndr.send(store.get_message(mid), _rendered(), "box1@rusprom.ru",
                    now=datetime(2025, 6, 4, 9, 0, tzinfo=UTC))
    assert res.ok
    assert store.list_events(event_type="division_gate_block", limit=5) == []


def test_tumbler_ne_snimaet_nastoyashchee_rashozhdenie(config, store, cards):
    """КЦ-ящик × Meyer-компания — комплаенс, тумблер тут ни при чём."""
    store.set_setting("allow_out_of_base", True)
    _cid, _rid, mid = _seed(store, inn=MEYER_INN)
    sndr = _sender(config, store, cards)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(store.get_message(mid), _rendered(), "box1@rusprom.ru",
                  now=datetime.now(UTC))
    evs = store.list_events(event_type="division_gate_block", limit=5)
    assert "mismatch" in evs[0].detail["reason"]


def test_tumbler_ne_snimaet_yashchik_bez_napravleniya(config, store, cards):
    store.set_setting("allow_out_of_base", True)
    _cid, _rid, mid = _seed(store, inn=KC_INN, mx="mailru")
    sndr = _sender(config, store, cards)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(store.get_message(mid), _rendered(), "box3@rusprom.ru",
                  now=datetime.now(UTC))
    evs = store.list_events(event_type="division_gate_block", limit=5)
    assert "mailbox_without_division" in evs[0].detail["reason"]
