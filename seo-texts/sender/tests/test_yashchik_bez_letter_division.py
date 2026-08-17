# -*- coding: utf-8 -*-
"""Пустой letter_division не должен открывать письму любой ящик.

Гейт направлений (Sender.division_block) читает panel.letter_division. Поле
ставит генератор, но его нет у писем, сделанных до его появления, и у части
новостных. При пустом поле _napravlenie_pisma возвращала None, и гейт
пропускал ЛЮБОЙ ящик — включая чужого направления.

Замер 17.08: 181 письмо из 1012 (17%) без поля, из них 13 уже отправлены.
В партии 935 поле есть всегда; пустые сидят в кампании 1 «новостные», а она
смешанная по направлениям — оттуда мейеровские письма и уходили с чужих
ящиков (владелец: «отправленные несколько мейер так были»).

Запасной источник — карточка компании в ТОЙ ЖЕ панели.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.sender import Sender  # noqa: E402


class _Msg:
    def __init__(self, mid=7):
        self.id = mid


class _Store:
    def __init__(self, panel):
        self._panel = panel
        self.звали = 0

    def confirm_review_for_message(self, mid):
        self.звали += 1
        return {"panel": self._panel}


def _sender(panel):
    s = Sender.__new__(Sender)
    s.store = _Store(panel)
    return s


def test_letter_division_glavnee_kartochki():
    """Явное поле письма сильнее карточки — карточка лишь запасная."""
    s = _sender({"letter_division": "kc", "company": {"division": "meyer"}})
    assert s._napravlenie_pisma(_Msg()) == "kc"


def test_pustoe_pole_beryot_kartochku():
    """Дыра, ради которой правка: поля нет, а направление известно."""
    s = _sender({"company": {"division": "meyer"}})
    assert s._napravlenie_pisma(_Msg()) == "meyer"


def test_sostavnoe_ne_reshaet():
    """«kc+meyer» — оба ящика законны, гейт остаётся на прежнем правиле."""
    s = _sender({"company": {"division": "kc+meyer"}})
    assert s._napravlenie_pisma(_Msg()) is None


def test_net_nichego_i_net_otveta():
    for panel in ({}, {"company": {}}, {"letter_division": ""},
                  {"company": {"division": None}}):
        assert _sender(panel)._napravlenie_pisma(_Msg()) is None, panel


def test_musor_v_polyah_ne_ronyaet():
    """Панель бывает чужой формы — гейт не смеет падать."""
    for panel in ({"company": "строка"}, {"company": []},
                  {"letter_division": 5}):
        assert _sender(panel)._napravlenie_pisma(_Msg()) is None, panel


def test_bez_message_v_bazu_ne_hodim():
    s = _sender({"company": {"division": "meyer"}})

    class _Пусто:
        id = None
    assert s._napravlenie_pisma(_Пусто()) is None
    assert s.store.звали == 0


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:120]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
