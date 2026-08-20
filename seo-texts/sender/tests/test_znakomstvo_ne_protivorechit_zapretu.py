# -*- coding: utf-8 -*-
"""Промпт не должен сам диктовать заход, который бракует заслон.

В блоке получателя стоят рядом две строки. Первая раздаёт формулу
знакомства ротацией по ZNAKOMSTVO: «ЕСЛИ ГОВОРИШЬ, ЧТО СМОТРЕЛ ИХ, скажи
это так: «Смотрел профиль…». Ровно этими словами». Вторая появляется,
когда квота партии исчерпала форму захода: «заход «от профиля»
израсходован, НЕ начинай письмо так: «Смотрел…», «Посмотрел…»».

Три формулы из восьми заслон относит именно к форме «от профиля», и на
таких письмах промпт противоречил сам себе. Модель слушалась первой
строки, гейт бракова́л по второй — письмо к тому моменту уже оплачено.
Замер партии 20.08: 4 брака из 13 на 30 письмах, и все четыре начинались
«Смотрел профиль».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import (ZNAKOMSTVO, _recipient_block,  # noqa: E402
                              форма_захода)

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC', contact_name='')


def _formula(блок):
    """Формула знакомства из блока промпта — или пусто, если строки нет."""
    for стр in блок.split('\n'):
        if 'ЕСЛИ ГОВОРИШЬ' in стр:
            return стр.split('«', 1)[1].split('…', 1)[0]
    return ''


def _блок(i, сменить=''):
    r = dict(БАЗА)
    r['extra'] = {'email': 'a@momez.ru'}
    if сменить:
        r['extra']['сменить_заход'] = сменить
    return _recipient_block(i, r, 'kc', 0)


def test_est_formuly_kotorye_zaslon_schitaet_profilem():
    """Иначе тест ниже проходил бы сам собой, ничего не проверяя."""
    свои = [з for з in ZNAKOMSTVO if форма_захода(з) == 'от профиля']
    assert len(свои) >= 3, свои


def test_ischerpannaya_forma_ne_razdayotsya():
    """Ни на одном сдвиге ротации запрещённая формула не выдаётся."""
    for i in range(3 * len(ZNAKOMSTVO)):
        ф = _formula(_блок(i, 'от профиля'))
        assert форма_захода(ф) != 'от профиля', (i, ф)


def test_bez_zapreta_formula_na_meste():
    """Без исчерпанной формы строка остаётся: разнообразие не режем."""
    формулы = {_formula(_блок(i)) for i in range(len(ZNAKOMSTVO))}
    assert '' not in формулы
    assert len(формулы) > 1, формулы


def test_zapret_drugoy_formy_ne_trogaet_profil():
    """Исчерпана «от вопроса» — формулы про «смотрел» раздаются как раньше."""
    формулы = {_formula(_блок(i, 'от вопроса'))
               for i in range(len(ZNAKOMSTVO))}
    assert формулы == set(ZNAKOMSTVO), формулы
