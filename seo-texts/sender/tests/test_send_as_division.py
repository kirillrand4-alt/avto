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


def _confirm(*, allowed=("kc", "meyer"), последний=None):
    from sender.confirm import ConfirmSend

    sender = SimpleNamespace(
        config=SimpleNamespace(mailboxes=lambda: list(ЯЩИКИ)),
        can_send_now=lambda mid, now=None, manual=False: True,
        pick_mailbox=lambda rec, camp, now=None, manual=False: "kc1@x.ru")
    cards = SimpleNamespace(active=True, divisions=lambda inn: set(allowed))

    def _last(*, among=None):
        # указатель ротации: как в Store.last_sent_mailbox(among=...)
        if among is not None and последний not in among:
            return None
        return последний

    c = ConfirmSend.__new__(ConfirmSend)          # без БД: нужен только подбор
    c._sender, c._cards = sender, cards
    c._store = SimpleNamespace(last_sent_mailbox=_last)
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
    assert [o["division"] for o in sa["options"]][:2] == ["meyer", "meyer"]


def test_гейт_направлений_не_расширяется():
    """Компании только с kc meyer-ящик не подставится, даже если письмо
    выглядит meyer-ским: prefer_division меняет порядок, а не права."""
    c = _confirm(allowed=("kc",))
    sa = c.send_as(_строка("фотосепаратор и рентген"), prefer_division="meyer")
    assert sa["mailbox_id"] == "kc1@x.ru"
    assert [o["division"] for o in sa["options"]] == ["kc", "kc"]


def test_ротация_внутри_направления():
    """Второе письмо подряд уходит со СЛЕДУЮЩЕГО meyer-ящика, а не с того же
    (#59: «не с одного всё отправлялось, а с разных по очереди»)."""
    # последним отправлял m1 -> очередь на m2
    sa = _confirm(последний="m1@y.ru").send_as(_строка("x", division_meta="meyer"))
    assert sa["mailbox_id"] == "m2@y.ru"
    # последним отправлял m2 -> круг замкнулся на m1
    sa = _confirm(последний="m2@y.ru").send_as(_строка("x", division_meta="meyer"))
    assert sa["mailbox_id"] == "m1@y.ru"


def test_чужой_указатель_не_ломает_круг_направления():
    """Компрессорных ящиков 14 против 4 Meyer, глобально последним почти всегда
    будет КЦ. Указатель обязан считаться ВНУТРИ направления, иначе Meyer-круг
    вечно начинался бы с первого адреса."""
    sa = _confirm(последний="kc2@x.ru").send_as(_строка("x", division_meta="meyer"))
    assert sa["mailbox_id"] == "m1@y.ru"        # указателя в круге нет -> с начала
    assert sa["options"][0]["division"] == "meyer"


def test_фильтр_оператора_подставляет_ящик_когда_направление_неизвестно():
    """Главная просьба владельца: открыл Meyer — отправитель Meyer.
    Направление письма не определяется, ключом становится фильтр очереди."""
    sa = _confirm().send_as(_строка("нейтральный текст без лексики"),
                            prefer_division="meyer")
    assert sa["letter_division"] is None
    assert sa["mailbox_id"] == "m1@y.ru"


def test_компания_вне_базы_всё_равно_получает_ящик_направления():
    """Владелец 28.07, ООО «Контрольный пакет»: компании нет в базе обзвона,
    поэтому список разрешённых направлений пуст. Раньше подбор уходил в ветку
    «направление неизвестно» и брал первый доступный ящик — компрессорный,
    хотя карточка лежала в очереди Meyer. Направление ПИСЬМА должно работать
    и здесь."""
    c = _confirm(allowed=())          # divisions() вернул пусто — вне базы
    sa = c.send_as(_строка("x", division_meta="meyer"))
    assert sa["mailbox_id"] == "m1@y.ru"
    # и порядок в выпадашке тот же
    assert [o["division"] for o in sa["options"]][:2] == ["meyer", "meyer"]


def test_вне_базы_ротация_тоже_работает():
    c = _confirm(allowed=(), последний="m1@y.ru")
    sa = c.send_as(_строка("x", division_meta="meyer"))
    assert sa["mailbox_id"] == "m2@y.ru"


def test_вне_базы_без_направления_поведение_прежнее():
    """Ни направления письма, ни фильтра — берём первый доступный, как раньше."""
    c = _confirm(allowed=())
    sa = c.send_as(_строка("нейтральный текст"))
    assert sa["mailbox_id"] == "kc1@x.ru"
