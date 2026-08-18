# -*- coding: utf-8 -*-
"""Когда свой пул выбран, письмо может уйти из другого — если тот чистый.

Владелец 18.08: «до лимита, но если после лимита ещё есть лимиты в другом
пуле, а в очереди ещё есть письма, можно перекинуть на яндекс например».

В тот день это стоило простоя: 273 письма на mail.ru лежали при нулевой
ёмкости своего пула (четыре ящика закрыл гейт репутации, два выбрали лимит)
и 276 свободных слотах у яндексового.

Плата понятна и ограничена: в запасные берём только ящики с долей жёстких
отбивок ниже порога, а сам перелив выключается одним ключом конфига.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.sender import Sender  # noqa: E402

СЕЙЧАС = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class _Реш:
    def __init__(self, value=0.0):
        self.value = value
        self.tripped = False


class _Гейты:
    def __init__(self, доли=None):
        self.доли = доли or {}

    def check_mailbox(self, mid):
        return _Реш(self.доли.get(mid, 0.0))

    def check_global(self):
        return _Реш()


class _Конфиг:
    def __init__(self, **ключи):
        self.ключи = ключи

    def get(self, key, default=None):
        return self.ключи.get(key, default)

    def provider_pools(self):
        return {"pool_mailru": ["mru1", "mru2"],
                "pool_yandex": ["ya1", "ya2"]}


def _сендер(могут, доли=None, **ключи):
    s = Sender.__new__(Sender)
    s.config = _Конфиг(**ключи)
    s.gates = _Гейты(доли)
    s.store = type("S", (), {"get_mailbox_state": staticmethod(lambda m: None)})()
    s.division_block = lambda r, mid, message=None: None
    s.can_send_now = lambda mid, now=None, manual=False: mid in могут
    s._day_key = lambda now: "2026-08-18"
    s._route_pool = lambda r, c: "pool_mailru"
    s._last_sent_mailbox = lambda: None
    return s


def test_bez_pereliva_pismo_zhdyot():
    """Умолчание — прежнее поведение: чужой пул не трогаем."""
    s = _сендер(могут={"ya1", "ya2"})
    assert s.pick_mailbox(None, None, now=СЕЙЧАС) is None


def test_pereliv_beryot_yashchik_chuzhogo_pula():
    s = _сендер(могут={"ya1", "ya2"}, **{"provider_split.overflow": True})
    assert s.pick_mailbox(None, None, now=СЕЙЧАС) in ("ya1", "ya2")


def test_svoy_pul_vsegda_pervyy():
    """Пока в своём есть кому слать, чужой не берём даже при переливе."""
    s = _сендер(могут={"mru2", "ya1"}, **{"provider_split.overflow": True})
    assert s.pick_mailbox(None, None, now=СЕЙЧАС) == "mru2"


def test_gryaznyy_yashchik_v_zapasnye_ne_beryom():
    """Смысл перелива — догрузить свободный ресурс, а не размазать отбивки."""
    s = _сендер(могут={"ya1", "ya2"}, доли={"ya1": 9.0, "ya2": 7.5},
                **{"provider_split.overflow": True,
                   "provider_split.overflow_max_bounce_pct": 3.0})
    assert s.pick_mailbox(None, None, now=СЕЙЧАС) is None


def test_porog_propuskaet_chistyy():
    s = _сендер(могут={"ya1", "ya2"}, доли={"ya1": 9.0, "ya2": 1.2},
                **{"provider_split.overflow": True,
                   "provider_split.overflow_max_bounce_pct": 3.0})
    assert s.pick_mailbox(None, None, now=СЕЙЧАС) == "ya2"


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:200]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
