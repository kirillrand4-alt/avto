# -*- coding: utf-8 -*-
"""Второй ответ клиента дописывает карточку лида, а не пропадает.

СЛУЧАЙ 25.08.2026. «Росткран» ответил дважды: сперва «интерес в 2
компрессорах», через пять часов — «Механик Александр +7 909 7865 379».
Второй ответ упёрся в ON CONFLICT DO NOTHING: в карточке остался только
первый, поле телефона пустое. Продавец видел «интересно» и не видел, кому
звонить, — лид пролежал шесть дней.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.store import Store  # noqa: E402


def _стор():
    s = Store(os.path.join(tempfile.mkdtemp(), "l.db"))
    s.init_schema()
    return s


def _лид(s, **правки):
    поля = dict(email="kto@zavod.ru", dedup_key="lead:t-1")
    поля.update(правки)
    return s.create_lead(**поля)


def test_pervyy_otvet_zavodit_kartochku():
    s = _стор()
    lid, created = _лид(s, need="Интерес в 2 компрессорах",
                        reply_kind="interested")
    assert created is True
    к = s.get_lead(lid)
    assert к.need == "Интерес в 2 компрессорах"


def test_vtoroy_otvet_dopisyvaetsya_sverhu():
    s = _стор()
    lid, _ = _лид(s, need="Интерес в 2 компрессорах", reply_kind="interested")
    lid2, created = _лид(s, need="Механик Александр +7 909 7865 379",
                         phone="+79097865379", reply_kind="hot")
    assert lid2 == lid and created is False
    к = s.get_lead(lid)
    assert к.need.startswith("Механик Александр"), "свежее должно быть сверху"
    assert "Интерес в 2 компрессорах" in к.need, "прежний ответ не теряем"
    assert к.phone == "+79097865379"
    assert к.reply_kind == "hot", "метку поднимаем вверх по важности"


def test_metku_vniz_ne_opuskaem():
    """Автоответ после живого «горячо» не должен гасить карточку."""
    s = _стор()
    lid, _ = _лид(s, need="Интересно", reply_kind="hot")
    _лид(s, need="Я в отпуске до 30.08", reply_kind="auto_reply")
    к = s.get_lead(lid)
    assert к.reply_kind == "hot"
    assert "отпуске" in к.need


def test_telefon_ne_zatiraem():
    s = _стор()
    lid, _ = _лид(s, need="раз", phone="+70000000001")
    _лид(s, need="два", phone="+70000000002")
    assert s.get_lead(lid).phone == "+70000000001", "первый контакт важнее"


def test_povtor_togo_zhe_otveta_ne_dvoit():
    s = _стор()
    lid, _ = _лид(s, need="Интерес в 2 компрессорах")
    _лид(s, need="Интерес в 2 компрессорах")
    к = s.get_lead(lid)
    assert к.need.count("Интерес в 2 компрессорах") == 1
