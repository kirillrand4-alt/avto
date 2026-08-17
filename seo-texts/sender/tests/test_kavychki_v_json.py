# -*- coding: utf-8 -*-
"""Прямая кавычка в теле письма не должна убивать оплаченный вызов.

17.08, сравнение уровней рассуждения: два письма из трёх умерли не на
правилах стиля, а на разборе - «Expecting ',' delimiter». Модель написала
в теле «газопровод "Сила Сибири"», кавычка закрыла строку раньше времени,
и весь ответ ушёл в мусор.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender import ai_letter as AL                             # noqa: E402


class TestKavychkiVnutri:
    def test_kavychka_v_tele_ekraniruetsya(self):
        сырое = '{"body": "газопровод "Сила Сибири" на участке"}'
        v = json.loads(AL._починить_json(сырое))
        assert v["body"] == 'газопровод "Сила Сибири" на участке'

    def test_zakryvayushchaya_pered_zapyatoy_ne_trogaetsya(self):
        сырое = '{"subject": "Тема", "body": "Тело"}'
        assert json.loads(AL._починить_json(сырое)) == {
            "subject": "Тема", "body": "Тело"}

    def test_zakryvayushchaya_pered_skobkoy(self):
        сырое = '{"letters": [{"idx": 0, "body": "текст"}]}'
        assert json.loads(AL._починить_json(сырое))["letters"][0]["idx"] == 0

    def test_uzhe_ekranirovannaya_ne_udvaivaetsya(self):
        сырое = '{"body": "он сказал \\"да\\" вчера"}'
        v = json.loads(AL._починить_json(сырое))
        assert v["body"] == 'он сказал "да" вчера'

    def test_perevod_stroki_vnutri_tela(self):
        сырое = '{"body": "Добрый день!\n\nПервый абзац."}'
        v = json.loads(AL._починить_json(сырое))
        assert v["body"].startswith("Добрый день!")
        assert "\n\n" in v["body"]

    def test_hvostovaya_zapyataya(self):
        assert json.loads(AL._починить_json('{"a": 1, "b": 2,}')) == {
            "a": 1, "b": 2}

    def test_parse_json_zhivoy_sluchay(self):
        # Ровно та форма, на которой сгорели письма: массив писем, в теле
        # прямые кавычки и переводы строк.
        сырое = ('```json\n{\n  "letters": [\n    {"idx": 0, '
                 '"subject": "Вопрос по компрессорам", '
                 '"body": "Добрый день!\n\nПрочитал про "Силу Сибири" - '
                 'объём работ серьёзный.\n\nС уважением,"}\n  ]\n}\n```')
        v = AL._parse_json(сырое, 'тест')
        тело = v["letters"][0]["body"]
        assert '"Силу Сибири"' in тело, тело
        assert тело.rstrip().endswith("С уважением,")
