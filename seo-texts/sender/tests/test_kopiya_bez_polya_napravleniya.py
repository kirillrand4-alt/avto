# -*- coding: utf-8 -*-
"""Копия второму контакту не должна уходить с ящика чужого направления.

СЛУЧАЙ. 20.08 два письма «Гастрофабрике» - «Для производства: контроль
включений в готовой продукции», тело про рентген-инспекцию и оптическую
сортировку, - ушли с компрессорных ящиков m.pavlov@kompressor-pro-trade.ru и
v.melnikov@kompressor-air-trade.ru и за подписью «Компрессор Центр». Владелец:
«когда вручную делал копии и отправлял, отправил не проверив направление».

ПОЧЕМУ ГЕЙТ МОЛЧАЛ. У карточек копий нет поля panel.letter_division (его
ставит генератор, а копию завели отдельно), метка компании составная
«kc+meyer» и направления не решает - авто-путь возвращал None и пропускал
любой ящик. Ручной экран те же письма спас бы: он смотрит ещё и лексику.

Теперь разборщик общий (sender.napravlenie_pisma), и лексика видна обоим.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.napravlenie_pisma import napravlenie_pisma  # noqa: E402
from sender.sender import Sender  # noqa: E402

ТЕЛО_МЕЙЕР = (
    "Меня зовут Владислав, представляю компанию «Руспром Meyer».\n"
    "Для готовой упакованной продукции применяется рентген-инспекция: "
    "оборудование выявляет металл, стекло, камень.\n"
    "Отдельно для сырья актуальна оптическая сортировка."
)
ТЕЛО_КЦ = (
    "Я занимаюсь промышленными системами сжатого воздуха и генерацией азота.\n"
    "Готов провести пневмоаудит компрессорного парка."
)


class _Msg:
    id = 3815


class _Store:
    def __init__(self, row):
        self._row = row

    def confirm_review_for_message(self, mid):
        return self._row


def _sender(row):
    s = Sender.__new__(Sender)
    s.store = _Store(row)
    return s


def test_kopiya_gastrofabriki_uznayotsya_po_tekstu():
    """Ровно та карточка, что ушла 20.08: поля нет, метка составная."""
    row = {"panel": {"company": {"division": "kc+meyer"}},
           "subject": "Для производства: контроль включений в готовой продукции",
           "body": ТЕЛО_МЕЙЕР}
    assert _sender(row)._napravlenie_pisma(_Msg()) == "meyer"


def test_kompressornaya_kopiya_ostayotsya_kc():
    row = {"panel": {}, "subject": "Вопрос по компрессорному парку",
           "body": ТЕЛО_КЦ}
    assert _sender(row)._napravlenie_pisma(_Msg()) == "kc"


def test_pole_generatora_silnee_leksiki():
    """Поле ставит генератор - оно и решает, даже если лексика спорит."""
    row = {"panel": {"letter_division": "kc"}, "subject": "рентген-инспекция",
           "body": ТЕЛО_МЕЙЕР}
    assert _sender(row)._napravlenie_pisma(_Msg()) == "kc"


def test_leksika_silnee_metki_kompanii():
    """Текст письма - прямая улика, метка базы - косвенная."""
    row = {"panel": {"company": {"division": "kc"}}, "subject": "",
           "body": ТЕЛО_МЕЙЕР}
    assert _sender(row)._napravlenie_pisma(_Msg()) == "meyer"


def test_obe_leksiki_srazu_ne_gadaem():
    row = {"panel": {}, "subject": "компрессор и рентген",
           "body": "сортировка и азот"}
    assert _sender(row)._napravlenie_pisma(_Msg()) is None


def test_pravlenyy_operatorom_tekst_tozhe_chitaetsya():
    """Оператор мог переписать письмо - гейт смотрит и правку."""
    row = {"panel": {}, "subject": "", "body": "",
           "edited_subject": "", "edited_body": ТЕЛО_МЕЙЕР}
    assert _sender(row)._napravlenie_pisma(_Msg()) == "meyer"


def test_razborshchik_ne_padaet_na_musore():
    for row in (None, {}, {"panel": "строка"}, {"panel": {"letter": "строка"}},
                {"subject": None, "body": None}):
        assert napravlenie_pisma(row) is None, row


def test_ruchnoy_ekran_i_avtootpravka_odinakovy():
    """Ради этого правка: два пути должны отвечать одно и то же."""
    from sender.confirm import ConfirmSend
    row = {"panel": {"company": {"division": "kc+meyer"}},
           "subject": "Для производства: контроль включений",
           "body": ТЕЛО_МЕЙЕР}
    экран = ConfirmSend.__new__(ConfirmSend)
    assert экран.letter_division(row) == _sender(row)._napravlenie_pisma(_Msg())
    assert экран.letter_division(row) == "meyer"
