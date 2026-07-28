# -*- coding: utf-8 -*-
"""Бренд в подписи следует направлению ЯЩИКА.

Владелец 28.07: «у писем которые на мейер отправляются почему-то в подписи
компрессорцентр». Причина — «Компрессор Центр» был зашит в _DEFAULT_SIGNATURE
одной строкой на все ящики. Юрлицо и ИНН при этом общие и меняться не должны:
ФЗ-38 требует атрибуцию по юрлицу, а не по направлению."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def _cfg(overrides=None):
    data = dict(overrides or {})

    def get(key, default=...):
        if key in data:
            return data[key]
        if default is ...:
            raise KeyError(key)
        return default
    return SimpleNamespace(get=get)


def test_бренд_по_направлению():
    from sender.sender import brand_for_division
    c = _cfg()
    assert brand_for_division(c, "meyer") == "Meyer"
    assert brand_for_division(c, "kc") == "Компрессор Центр"


def test_неизвестное_направление_остаётся_кц():
    """Пустое/чужое направление не должно превращать подпись в пустую строку."""
    from sender.sender import brand_for_division
    c = _cfg()
    assert brand_for_division(c, None) == "Компрессор Центр"
    assert brand_for_division(c, "") == "Компрессор Центр"
    assert brand_for_division(c, "xxx") == "Компрессор Центр"


def test_бренд_переопределяется_конфигом():
    from sender.sender import brand_for_division
    c = _cfg({"personalization.brand_by_division": {"meyer": "Meyer Рус"}})
    assert brand_for_division(c, "meyer") == "Meyer Рус"
    assert brand_for_division(c, "kc") == "Компрессор Центр"


def test_шаблон_подписи_подставляет_бренд():
    """Дефолтный шаблон обязан иметь {brand}, иначе правка ничего не меняет."""
    from sender.sender import Sender, brand_for_division
    tmpl = Sender._DEFAULT_SIGNATURE
    assert "{brand}" in tmpl and "Компрессор Центр" not in tmpl
    sig = tmpl.format(name="Анастасия Мирошниченко", role="Менеджер по продажам",
                      inn="2221239841", brand=brand_for_division(_cfg(), "meyer"))
    assert "«Meyer»" in sig
    # юрлицо и ИНН общие — направление их не подменяет
    assert "ООО «Руспром», ИНН 2221239841" in sig
