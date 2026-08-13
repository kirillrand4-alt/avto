# -*- coding: utf-8 -*-
"""Один ИНН на все письма и согласование рода отправителя.

Владелец 13.08: «ИНН у нас один 2221239841... сделай и исправь ИНН в будущих
письмах, а также проверку на пол сделай, там признателен есть когда пишет
девушка».

Оба бага одной природы: поле задаётся в одном месте, а проверять его было
некому. У кампаний Meyer в legal_inn стоял чужой ИНН — три письма ушли с
неверной атрибуцией. Словарь согласования рода знал «благодарен» и не знал
«признателен» — а он в концовке КАЖДОГО письма, 729 вхождений по замеру.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from sender.confirm import ConfirmBlockedError, ConfirmSend  # noqa: E402
from sender.gender_agree import agree, gender_of  # noqa: E402

НАШ = "2221239841"


# --- род отправителя --------------------------------------------------------- #

КОНЦОВКА = ("Если тема сейчас неактуальна, буду признателен за короткий ответ, "
            "чтобы в дальнейшем вас не отвлекать.")


def test_priznatelen_soglasuetsya():
    """Тот самый пропуск: 729 писем уходили с мужской формой при женской подписи."""
    assert "буду признательна" in agree(КОНЦОВКА, "f")
    assert "признателен" not in agree(КОНЦОВКА, "f")


def test_muzhchine_nichego_ne_menyaem():
    assert agree(КОНЦОВКА, "m") == КОНЦОВКА


def test_idempotentno():
    один = agree(КОНЦОВКА, "f")
    assert agree(один, "f") == один


def test_ostalnye_formy_iz_zamera():
    пары = [("Смотрел профиль «Лука».", "Смотрела"),
            ("Изучил профиль компании.", "Изучила"),
            ("Обратился по вопросу контроля.", "Обратилась"),
            ("Заглянул на ваш сайт.", "Заглянула"),
            ("Решил написать вам.", "Решила"),
            ("Проверил параметры линии.", "Проверила")]
    for исход, ждём in пары:
        assert ждём in agree(исход, "f"), исход


def test_tretye_litso_ne_trogaem():
    """«Завод запустил линию» — не про отправителя, править нельзя."""
    т = "Завод запустил линию. Поставщик обратился к нам."
    assert agree(т, "f") == т


def test_pol_yashchikov_paneli():
    assert gender_of("Ирина Кузнецова") == "f"
    assert gender_of("Анастасия Мирошниченко, Meyer") == "f"
    assert gender_of("Антон Балакирев") == "m"
    assert gender_of("Никита Морозов") == "m"       # -а, но мужское


# --- один ИНН ---------------------------------------------------------------- #

class _Юр:
    def __init__(self, inn):
        self.inn = inn


class _Конфиг:
    def __init__(self, inn=НАШ):
        self._inn = inn

    def legal(self):
        return _Юр(self._inn)

    def get(self, ключ, умолч=None):
        return умолч


class _Кампания:
    def __init__(self, inn):
        self.legal_inn = inn


class _Хранилище:
    def __init__(self, inn):
        self._inn = inn

    def get_campaign(self, _cid):
        return _Кампания(self._inn)


def _confirm(inn_кампании=НАШ, наш=НАШ):
    c = ConfirmSend.__new__(ConfirmSend)
    c._config = _Конфиг(наш)
    c._store = _Хранилище(inn_кампании)
    return c


def test_chuzhoy_inn_kampanii_lovitsya():
    """Ровно случай Meyer: у кампании стоял московский 7743013968."""
    причина = _confirm("7743013968")._chuzhoy_inn(
        {"campaign_id": 8, "body": "текст"})
    assert причина and "7743013968" in причина and НАШ in причина


def test_nash_inn_prohodit():
    assert _confirm(НАШ)._chuzhoy_inn({"campaign_id": 5, "body": "текст"}) is None


def test_pustoy_inn_kampanii_ne_brak():
    """Пусто — подпись возьмёт ИНН из конфига, он и есть верный."""
    assert _confirm("")._chuzhoy_inn({"campaign_id": 5, "body": "т"}) is None


def test_chuzhoy_inn_v_tele_pisma():
    """Оператор мог вписать руками при правке."""
    строка = {"campaign_id": 5,
              "body": "С уважением,\nООО «Руспром», ИНН 7743013968"}
    причина = _confirm(НАШ)._chuzhoy_inn(строка)
    assert причина and "7743013968" in причина


def test_nash_inn_v_tele_prohodit():
    строка = {"campaign_id": 5, "body": f"ООО «Руспром», ИНН {НАШ}"}
    assert _confirm(НАШ)._chuzhoy_inn(строка) is None


def test_bez_konfiga_zaslon_molchit():
    """Не с чем сверять — отправку не рвём."""
    c = ConfirmSend.__new__(ConfirmSend)
    c._config = _Конфиг("")
    c._store = _Хранилище("7743013968")
    assert c._chuzhoy_inn({"campaign_id": 8, "body": "т"}) is None


def test_zaslon_podklyuchyon_k_approve():
    import inspect

    исходник = inspect.getsource(ConfirmSend.approve)
    assert "_chuzhoy_inn" in исходник
    assert "чужой and not force" in исходник
