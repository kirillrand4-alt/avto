# -*- coding: utf-8 -*-
"""Ящик отправки выбирается по направлению ПИСЬМА, а не по компании.

Владелец 28.07: «в мейер подставлялись мейер почты в первую очередь».
У компании «kc+meyer» гейт пропускает оба направления, и подбор брал первый
ящик по конфигу — то есть всегда компрессорный, даже под письмо про
фотосепараторы (и подпись уходила чужая)."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def _ящик(mid, division, from_name):
    return SimpleNamespace(mailbox_id=mid, division=division,
                           from_name=from_name, email=mid)


ЯЩИКИ = [                      # порядок как в конфиге: КЦ идут первыми
    _ящик("kc1@x.ru", "kc", "Владислав"),
    _ящик("kc2@x.ru", "kc", "Игорь"),
    _ящик("m1@y.ru", "meyer", "Анастасия"),
    _ящик("m2@y.ru", "meyer", "Андрей"),
]


def _confirm(*, allowed=("kc", "meyer")):
    from sender.confirm import ConfirmSend

    sender = SimpleNamespace(
        config=SimpleNamespace(mailboxes=lambda: list(ЯЩИКИ)),
        can_send_now=lambda mid, now=None, manual=False: True,
        pick_mailbox=lambda rec, camp, now=None, manual=False: "kc1@x.ru")
    cards = SimpleNamespace(active=True, divisions=lambda inn: set(allowed))
    c = ConfirmSend.__new__(ConfirmSend)          # без БД: нужен только подбор
    c._sender, c._cards = sender, cards
    return c


def _строка(текст, *, division_meta=None, panel_extra=None):
    panel = {"company": {"division": "kc+meyer"}}
    if division_meta is not None:
        panel["letter_division"] = division_meta
    panel.update(panel_extra or {})
    return {"id": 1, "inn": "7700000000", "email": "a@x.ru",
            "subject": "тема", "body": текст, "panel": panel}


def test_meyer_письмо_подставляет_meyer_ящик():
    """Метка генератора letter_division — главный источник."""
    sa = _confirm().send_as(_строка("любой текст", division_meta="meyer"))
    assert sa["mailbox_id"] == "m1@y.ru"
    assert sa["letter_division"] == "meyer"
    # и в выпадашке meyer-ящики идут первыми
    assert [o["division"] for o in sa["options"]][:2] == ["meyer", "meyer"]


def test_направление_угадывается_по_лексике_письма():
    """Письма, легшие в очередь до появления метки, разбираются по тексту."""
    sa = _confirm().send_as(_строка(
        "Предлагаем фотосепараторы и рентген-инспекцию для линии сортировки."))
    assert sa["mailbox_id"] == "m1@y.ru"
    assert sa["letter_division"] == "meyer"


def test_компрессорное_письмо_остаётся_на_кц():
    sa = _confirm().send_as(_строка(
        "Винтовой компрессор и подготовка сжатого воздуха для цеха."))
    assert sa["mailbox_id"] == "kc1@x.ru"
    assert sa["letter_division"] == "kc"


def test_смешанная_лексика_не_угадывается():
    """Обе лексики сразу — не гадаем, работает обычный подбор."""
    sa = _confirm().send_as(_строка(
        "И компрессор, и фотосепаратор — оба направления."))
    assert sa["letter_division"] is None
    assert sa["mailbox_id"] == "kc1@x.ru"       # первый по конфигу, как раньше


def test_фильтр_оператора_поднимает_свои_ящики_в_списке():
    """Направление письма неизвестно — порядок задаёт фильтр КЦ/Meyer."""
    sa = _confirm().send_as(_строка("нейтральный текст без лексики"),
                            prefer_division="meyer")
    assert sa["letter_division"] is None
    assert [o["division"] for o in sa["options"]][:2] == ["meyer", "meyer"]
    # подстановка при этом не выдумывается — это по-прежнему обычный подбор
    assert sa["mailbox_id"] == "kc1@x.ru"


def test_гейт_направлений_не_расширяется():
    """Компании только с kc meyer-ящик не подставится, даже если письмо
    выглядит meyer-ским: prefer_division меняет порядок, а не права."""
    c = _confirm(allowed=("kc",))
    sa = c.send_as(_строка("фотосепаратор и рентген"), prefer_division="meyer")
    assert sa["mailbox_id"] == "kc1@x.ru"
    assert [o["division"] for o in sa["options"]] == ["kc", "kc"]
