# -*- coding: utf-8 -*-
"""Точные числа паспорта: расхождение источников и слабая атрибуция сайта.

Оба правила родились из сверки 16.08 (три письма на трёх моделях). Разбор
карточки НПФ «Метмаш» показал две дыры сразу: в ключе «мощности» лежали
одновременно «более чем 350 единиц» и «более 400 единиц» с их же сайта, а
сам сайт был помечен как доказанный слабо. Модель взяла точное число — и
оно было настоящим, но проверить его получатель мог только опровержением.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender import ai_letter as AL                            # noqa: E402


class TestRashozhdenieChisel:
    def test_dva_raznyh_chisla_v_odnom_pokazatele_sporny(self):
        спор = AL._rashodyashchiesya_chisla([
            "Производственные мощности состоят из более чем 350 единиц "
            "металлообрабатывающего оборудования.",
            "Производственные мощности включают более 400 единиц "
            "металлообрабатывающего оборудования.",
        ])
        assert спор == {'350', '400'}, спор

    def test_diapazon_v_odnoy_stroke_ne_spor(self):
        # «6 000 – 7 000 тонн» — это диапазон, а не разночтение источников.
        assert AL._rashodyashchiesya_chisla([
            "мощности завода позволяют оцинковывать 6 000 – 7 000 тонн "
            "металлоконструкций в месяц.",
        ]) == set()

    def test_raznye_pokazateli_ne_putayutsya(self):
        # Тонны ограждений и тонны металлоконструкций — разные показатели,
        # спорить между собой они не могут.
        assert AL._rashodyashchiesya_chisla([
            "позволяют выпускать до 5 000 тонн ограждений в месяц.",
            "позволяют оцинковывать 7 000 тонн металлоконструкций в месяц.",
        ]) == set()

    def test_odinakovoe_chislo_dvazhdy_ne_spor(self):
        assert AL._rashodyashchiesya_chisla([
            "Общая производственная площадь 10 000 кв. м.",
            "Общая производственная площадь 10 000 кв. м.",
        ]) == set()

    def test_kartochka_preduprezhdaet_o_raskhozhdenii(self):
        рек = {'company_name': 'ООО НПФ "МЕТМАШ"', 'mode': 'GENERIC',
               'okved': '25.62', 'extra': {'verified': 'inn', 'site_facts': {
                   'мощности': [
                       "состоят из более чем 350 единиц металлообрабатывающего "
                       "оборудования",
                       "включают более 400 единиц металлообрабатывающего "
                       "оборудования"]}}}
        б = AL._recipient_block(0, рек, 'kc', 0)
        assert 'числа выше расходятся между собой' in б, б
        assert '350' in б and '400' in б, б

    def test_spornoe_chislo_ne_v_belom_spiske(self):
        extra = {'verified': 'inn', 'site_facts': {'мощности': [
            "более чем 350 единиц оборудования",
            "более 400 единиц оборудования"]}}
        разрешено = AL.allowed_numbers({}, extra, 'kc')
        assert '350' not in разрешено and '400' not in разрешено

    def test_bessporное_chislo_ostayotsya_razreshennym(self):
        extra = {'verified': 'inn', 'site_facts': {'мощности': [
            "Общая производственная площадь 10 000 кв. м."]}}
        assert '10' in AL.allowed_numbers({}, extra, 'kc')


class TestSlabayaAtributsiya:
    @pytest.mark.parametrize('признак', ['phone', 'provider', 'mismatch'])
    def test_chisla_slabogo_sayta_zapreshcheny(self, признак):
        extra = {'verified': признак, 'site_facts': {
            'мощности': ["до 5000 тонн ограждений в месяц"]}}
        assert '5000' not in AL.allowed_numbers({}, extra, 'kc')

    def test_dokazannyy_sayt_chisla_razreshaet(self):
        extra = {'verified': 'inn', 'site_facts': {
            'мощности': ["до 5000 тонн ограждений в месяц"]}}
        assert '5000' in AL.allowed_numbers({}, extra, 'kc')

    def test_god_osnovaniya_perezhivaet_slabuyu_atributsiyu(self):
        # Год с сайта — не тот факт, которым можно опозориться: он совпадает
        # с ЕГРЮЛ и проверяется. Ради него запрет не расширяем.
        extra = {'verified': 'phone', 'site_facts': {'год_основания': '1999'}}
        assert '1999' in AL.allowed_numbers({}, extra, 'kc')

    def test_kartochka_zapreshchaet_tochnye_chisla_slovami(self):
        рек = {'company_name': 'ООО "ЗАВОД"', 'mode': 'GENERIC',
               'okved': '25.11', 'extra': {'verified': 'phone'}}
        б = AL._recipient_block(0, рек, 'kc', 0)
        assert 'НЕ называть точных чисел с сайта' in б, б


class TestGipotezaNeFakt:
    """Строку-ориентир модели читали как перечень цехов получателя."""

    def test_bez_cehov_stroka_pomechena_gipotezoy(self):
        рек = {'company_name': 'ООО "ИТС МК"', 'mode': 'GENERIC',
               'okved': '25.11', 'extra': {}}
        б = AL._recipient_block(0, рек, 'kc', 0)
        assert 'НАША ГИПОТЕЗА ПО ОТРАСЛИ, НЕ ФАКТ О НИХ' in б, б
        assert 'ЗАПРЕЩЕНО' in б, б

    def test_s_cehami_zapret_snyat(self):
        рек = {'company_name': 'ООО "ТОЧИНВЕСТ"', 'mode': 'GENERIC',
               'okved': '25.11', 'extra': {'verified': 'inn', 'site_facts': {
                   'оборудование_линии': ['Автоматическая линия цинкования '
                                          'трубы']}}}
        б = AL._recipient_block(0, рек, 'kc', 0)
        assert 'Их настоящие цеха названы выше' in б, б
        assert 'НАША ГИПОТЕЗА ПО ОТРАСЛИ' not in б, б

    def test_zagolovok_ne_pro_szhatyy_vozduh_u_meyer(self):
        # Заголовок общий для обоих направлений: у Meyer речь о сортировке,
        # и компрессорная лексика в его карточке — прямая ошибка.
        рек = {'company_name': 'ООО "МЕЛЬНИЦА"', 'mode': 'GENERIC',
               'okved': '10.61', 'extra': {}}
        б = AL._recipient_block(0, рек, 'meyer', 0)
        assert 'воздух' not in б.split('ГИПОТЕЗА ПО ОТРАСЛИ')[-1].lower()
