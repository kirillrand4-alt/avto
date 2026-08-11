"""Автоответ как лид + копия письма на подсказанный адрес.

11.08 владелец спросил, почему ответ не попал в лиды. Ответ: письмо было
автоответом (Auto-Submitted: auto-replied), классификатор отработал верно.
Но внутри лежал новый рабочий адрес, и его никто не подхватывал: за месяц
автоответов было два, и адрес был в ОБОИХ.

Здесь защищается: адрес находится, свои домены и служебные autoreply@ не
принимаются за контакт, копия письма ставится в очередь и не задваивается.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.avtootvet import (адреса_из_автоответа,  # noqa: E402
                              переслать_на_новый_адрес, разобрать_автоответ)

ГЛАДИУМ = ("Добрый день! С 27.07 по 9.08 нахожусь в отпуске. "
           "По всем вопросам прошу обращаться к Александру Белоусу "
           "belous.a@gladium.ru")
ФАРМО = ("Информируем вас о создании общего адреса рассылки. Сотрудниками "
         "ООО НИЦ «ФАРМОБОРОНА» создан единый общий адрес client@farmoborona.ru "
         "Просим не использовать другие электронные адреса")


def test_adres_iz_otpuska():
    assert адреса_из_автоответа(
        ГЛАДИУМ, от_кого="Денис Бабакин <babakin.d@gladium.ru>") == \
        ["belous.a@gladium.ru"]


def test_adres_iz_obshchego_yashchika():
    assert адреса_из_автоответа(
        ФАРМО, от_кого="Колчанова <kolchanova_alena@farmoborona.ru>") == \
        ["client@farmoborona.ru"]


def test_svoi_i_sluzhebnye_ne_kontakt():
    """В автоответе цитируется НАШЕ письмо с подписью — это не новый контакт."""
    текст = ("Я в отпуске. Ваше письмо: от i.lyapin@kompressor-air-expert.ru, "
             "ответы на kolchanova_alena.autoreply@farmoborona.ru, "
             "пишите на zam@zavod.ru")
    assert адреса_из_автоответа(текст, от_кого="x@zavod.ru") == ["zam@zavod.ru"]


def test_adres_otpravitelya_ne_schitaetsya_novym():
    assert адреса_из_автоответа("пишите мне: babakin.d@gladium.ru",
                                от_кого="<babakin.d@gladium.ru>") == []


class _Store:
    def __init__(self, письмо=None):
        self.письмо = письмо
        self.поставлено = []
        self._n = 0

    def poslednee_otpravlennoe(self, recipient_id):
        return self.письмо

    def confirm_submit(self, **kw):
        self._n += 1
        # идемпотентность по dedup_key — как в настоящем хранилище
        for k in self.поставлено:
            if k["dedup_key"] == kw["dedup_key"]:
                return (k["id"], False)
        kw["id"] = self._n
        self.поставлено.append(kw)
        return (self._n, True)


ПИСЬМО = {"subject": "Вопрос по системе сжатого воздуха", "body": "Тело письма",
          "edited_subject": None, "edited_body": None, "campaign_id": 5,
          "inn": "7712345678"}


def test_kopiya_pisma_v_ochered():
    s = _Store(ПИСЬМО)
    rid = переслать_на_новый_адрес(s, recipient_id=7,
                                   адрес="belous.a@gladium.ru")
    assert rid == 1
    з = s.поставлено[0]
    assert з["email"] == "belous.a@gladium.ru"
    assert з["subject"] == "Вопрос по системе сжатого воздуха"
    assert з["body"] == "Тело письма"
    assert з["status"] == "pending"            # ждёт оператора, не уходит само
    assert "автоответ дал новый адрес" in з["reason"]
    assert з["panel"]["ishodnyy_poluchatel"] == 7


def test_pravka_operatora_pobezhdaet():
    """Человек получил ОТРЕДАКТИРОВАННЫЙ текст — его и пересылаем."""
    s = _Store(dict(ПИСЬМО, edited_subject="Правленая тема",
                    edited_body="Правленое тело"))
    переслать_на_новый_адрес(s, recipient_id=7, адрес="zam@zavod.ru")
    assert s.поставлено[0]["subject"] == "Правленая тема"
    assert s.поставлено[0]["body"] == "Правленое тело"


def test_povtor_ne_zadvaivaet():
    s = _Store(ПИСЬМО)
    a = переслать_на_новый_адрес(s, recipient_id=7, адрес="zam@zavod.ru")
    b = переслать_на_новый_адрес(s, recipient_id=7, адрес="zam@zavod.ru")
    assert a == b and len(s.поставлено) == 1


def test_bez_ishodnogo_pisma_nichego_ne_stavim():
    s = _Store(None)
    assert переслать_на_новый_адрес(s, recipient_id=7, адрес="x@y.ru") is None
    assert s.поставлено == []


def test_razbor_tselikom():
    s = _Store(ПИСЬМО)
    итог = разобрать_автоответ(s, recipient_id=7, текст=ФАРМО,
                               от_кого="<kolchanova_alena@farmoborona.ru>")
    assert итог["адреса"] == ["client@farmoborona.ru"]
    assert len(итог["постановки"]) == 1
