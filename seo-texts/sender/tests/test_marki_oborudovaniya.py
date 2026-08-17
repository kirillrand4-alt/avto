# -*- coding: utf-8 -*-
"""Марки оборудования в холодном письме — брак.

Найдено сплошной проверкой партии 17.08. Письмо «Газпром газораспределение
Дальний Восток» обещало подобрать «аналоги оборудования, которое раньше
покупали у Atlas Copco или Kaeser». Две беды в одной фразе: мы утверждаем,
что они покупали (в паспорте про их парк нет ни слова), и называем чужие
торговые марки в письме от лица юрлица.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender import ai_letter as AL                             # noqa: E402


class TestMarki:
    @pytest.mark.parametrize('фраза', [
        'подобрать аналоги того, что покупали у Atlas Copco',
        'машины Kaeser обслуживать стало дорого',
        'вместо Ingersoll Rand ставим наше',
        'у вас, кажется, Ремеза',
        'аналог Атлас Копко',
        'поставляем Enger и Berg',
        'Dalgakiran больше не возят',
    ])
    def test_marka_lovitsya(self, фраза):
        assert AL.marki_oborudovaniya(фраза), фраза

    @pytest.mark.parametrize('фраза', [
        'нам дали заявку на компрессор',
        'вы отдали предпочтение винтовым машинам',
        'берег реки рядом с площадкой',
        'кайзер — фамилия вашего главного инженера',
        'абаканский завод металлоконструкций',
        'компрессорный парк работает под нагрузкой',
    ])
    def test_zhivaya_rech_ne_lovitsya(self, фраза):
        assert AL.marki_oborudovaniya(фраза) == [], фраза

    def test_svoyo_imya_ne_marka(self):
        # Руспром, Компрессор Центр и Meyer — наша подпись и представление
        # по канону редактора, а не марка оборудования.
        тело = ('Я веду компрессорное направление в Компрессор Центре.\n'
                'С уважением,\nООО «Руспром»')
        assert AL.marki_oborudovaniya(тело) == []
        assert AL.marki_oborudovaniya('представляю «Руспром Meyer»') == []

    def test_neskolko_marok_v_odnoy_stroke(self):
        r = AL.marki_oborudovaniya('покупали у Atlas Copco или Kaeser')
        assert len(r) == 1 and 'atlas copco' in r[0] and 'kaeser' in r[0], r

    def test_gate_brakuet_pismo_s_markoy(self):
        тело = ('Добрый день!\n\nНа объектах газораспределения компрессоры '
                'работают под нагрузкой: продувка, опрессовка, пневмоинструмент. '
                'Помогаю подбирать аналоги оборудования, которое раньше '
                'покупали у Atlas Copco или Kaeser.\n\nПодскажите, актуален ли '
                'вопрос обновления парка?\n\nС уважением,')
        fails = AL.gate('Вопрос по компрессорам', тело, mode='GENERIC',
                        extra={'company_name': 'ООО «Завод»'},
                        facts={}, division='kc')
        assert any('марка оборудования' in str(f) for f in fails), fails
