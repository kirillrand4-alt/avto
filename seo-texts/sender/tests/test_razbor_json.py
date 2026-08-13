# -*- coding: utf-8 -*-
"""Разбор ответа модели устойчив к типовым поломкам (13.08).

Повод: перегенерация письма #952 упала с «Expecting property name enclosed in
double quotes». Разбор брал кусок от ПЕРВОЙ «{» до последней, а в правилах и
пуле механик стоят плейсхолдеры «{news_object}»/«{city}» — модель повторила их
эхом в преамбуле, и кусок начинался с эха. Три вызова подряд, три брака, письмо
не перегенерировано.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sender.ai_letter import _parse_json  # noqa: E402

ПОЛЕЗНОЕ = ('{"letters": [{"idx": 0, "subject": "Вопрос по контролю", '
            '"body": "Добрый день!"}]}')


def test_eho_placeholdera_pered_otvetom():
    """Тот самый случай: модель проговорила механику с плейсхолдером."""
    ответ = ("Беру механику «Предусмотрен ли контроль включений в проекте "
             "{news_object}?» и город {city}.\n\n" + ПОЛЕЗНОЕ)
    assert _parse_json(ответ, "meyer-0")["letters"][0]["idx"] == 0


def test_skobka_v_tele_pisma_ne_lomaet_balans():
    ответ = '{"letters": [{"idx": 0, "body": "Смета { без пары"}]}'
    assert _parse_json(ответ, "t")["letters"][0]["body"] == "Смета { без пары"


def test_kodovyy_zabor_i_hvost():
    ответ = "Готово:\n```json\n" + ПОЛЕЗНОЕ + "\n```\nЕсли нужно — поправлю."
    assert "letters" in _parse_json(ответ, "t")


def test_beryotsya_poleznaya_nagruzka_a_ne_primer():
    """Маленький разбираемый объект перед ответом не должен победить."""
    ответ = '{"пример": 1}\n\n' + ПОЛЕЗНОЕ
    assert "letters" in _parse_json(ответ, "t")


def test_hvostovaya_zapyataya_chinitsya():
    ответ = '{"letters": [{"idx": 0, "body": "Текст",}],}'
    assert _parse_json(ответ, "t")["letters"][0]["idx"] == 0


def test_syroy_perevod_stroki_v_tele():
    """Тело письма многострочное — модель иногда не экранирует \\n."""
    ответ = '{"letters": [{"idx": 0, "body": "Добрый день!\n\nМеня зовут"}]}'
    вышло = _parse_json(ответ, "t")["letters"][0]["body"]
    assert вышло == "Добрый день!\n\nМеня зовут"


def test_net_json_govorit_chto_prishlo():
    with pytest.raises(ValueError) as e:
        _parse_json("Извините, не могу выполнить запрос.", "meyer-0")
    assert "Извините" in str(e.value)


def test_bityy_json_pokazyvaet_otvet():
    with pytest.raises(ValueError) as e:
        _parse_json("{не json вовсе}", "t")
    assert "не json вовсе" in str(e.value)


def test_obychnyy_otvet_bez_musora():
    assert _parse_json(ПОЛЕЗНОЕ, "t")["letters"][0]["subject"] == "Вопрос по контролю"
