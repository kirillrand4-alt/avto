# -*- coding: utf-8 -*-
"""Оборванный ответ модели не выбрасывается целиком.

17.08, партия на opus-4.8: два письма из шести упали с «нет JSON в ответе»,
а ответ начинался с ```json\\n{"letters": [{"idx":… и просто не имел конца -
модель упёрлась в потолок max_tokens. Оплаченный вызов уходил в мусор
вместе с письмами, которые она успела дописать до обрыва.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender import ai_letter as AL                             # noqa: E402


class TestDobratObryv:
    def test_oborvannyy_obekt_zakryvaetsya(self):
        assert AL._dobrat_obryv('{"a": 1, "b": 2') == '{"a": 1, "b": 2}'

    def test_oborvannaya_stroka_zakryvaetsya(self):
        достр = AL._dobrat_obryv('{"subject": "Вопрос по компрес')
        assert достр.endswith('"}'), достр

    def test_vlozhennye_skobki_v_obratnom_poryadke(self):
        достр = AL._dobrat_obryv('{"letters": [{"idx": 0, "body": "текст')
        assert достр == '{"letters": [{"idx": 0, "body": "текст"}]}', достр

    def test_tselyy_json_ne_trogaem(self):
        assert AL._dobrat_obryv('{"a": 1}') == ''

    def test_musor_bez_skobok(self):
        assert AL._dobrat_obryv('просто текст') == ''

    def test_skobka_vnutri_stroki_ne_schitaetsya(self):
        # «{city}» в тексте письма не должна ломать стек.
        достр = AL._dobrat_obryv('{"body": "плейсхолдер {city} внутри"')
        assert достр == '{"body": "плейсхолдер {city} внутри"}', достр


class TestParseJson:
    def test_zaborchik_ne_meshaet(self):
        v = AL._parse_json('```json\n{"letters": [{"idx": 0}]}\n```', 'т')
        assert v == {"letters": [{"idx": 0}]}

    def test_oborvannyy_otvet_razbiraetsya(self):
        сырое = ('```json\n{\n  "letters": [\n    {"idx": 0, "subject": "А",'
                 ' "body": "первое письмо целиком"},\n'
                 '    {"idx": 1, "subject": "Б", "body": "второе оборвал')
        v = AL._parse_json(сырое, 'т')
        письма = v["letters"]
        assert len(письма) == 2
        assert письма[0]["body"] == "первое письмо целиком"

    def test_oshibka_pokazyvaet_dlinu_i_hvost(self):
        with pytest.raises(ValueError) as e:
            AL._parse_json("ответ вообще без фигурных скобок", 'т')
        текст = str(e.value)
        assert "длина" in текст and "хвост" in текст, текст
