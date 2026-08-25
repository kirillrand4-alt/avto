"""Повтор после ответа без JSON идёт С ОКРИКОМ, а не тем же промптом.

Замер 25.08 по логам прогонов: из 47 браков мейеровского блока 25 — «нет
JSON в ответе», ответ начинался с «Профиль получателя…»; в компрессорном
блоке так ушло 57 писем. Три попытки были и раньше, но все три уходили
слово в слово одинаковыми, и модель рассуждала трижды. Каждая попытка
оплачена и выброшена.
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_letter import AiLetterGen, ОКРИК_JSON  # noqa: E402


def _ген(ответы):
    """Генератор, чей вызов модели отдаёт заготовленные ответы по очереди."""
    спрошено = []

    def зов(prompt):
        спрошено.append(prompt)
        return ответы[min(len(спрошено) - 1, len(ответы) - 1)]

    g = AiLetterGen(зов)
    return g, спрошено


def test_pervaya_popytka_bez_okrika():
    g, спрошено = _ген(['{"letters": []}'])
    g._ask("ПРОМПТ", "genkc0")
    assert спрошено == ["ПРОМПТ"], "первый вызов должен идти чистым промптом"


def test_povtor_neset_okrik():
    """Проза в первом ответе → второй вызов с окриком и уже разбирается."""
    g, спрошено = _ген(["Профиль получателя — производство упаковки, поэтому…",
                        '{"letters": [{"idx": 0}]}'])
    итог = g._ask("ПРОМПТ", "genmeyer0")
    assert итог == {"letters": [{"idx": 0}]}
    assert len(спрошено) == 2
    assert спрошено[0] == "ПРОМПТ"
    assert спрошено[1] == "ПРОМПТ" + ОКРИК_JSON


def test_okrik_v_hvoste_promta():
    """Окрик дописан в ХВОСТ: кэш промпта живёт префиксом, и добавка в
    начале обнулила бы его на каждой повторной попытке."""
    g, спрошено = _ген(["не json", "не json", "не json"])
    with pytest.raises(RuntimeError):
        g._ask("ПРОМПТ", "genkc0")
    assert спрошено[1].startswith("ПРОМПТ")
    assert спрошено[2].startswith("ПРОМПТ")
    assert "JSON" in спрошено[1]


def test_vse_popytki_bez_json_dayut_oshibku_s_tegom():
    g, спрошено = _ген(["ни разу не json"])
    with pytest.raises(RuntimeError) as ex:
        g._ask("ПРОМПТ", "genmeyer0")
    assert "genmeyer0" in str(ex.value)
    assert len(спрошено) == 3, "попыток по-прежнему три"


# --- длинное тире чиним, а не бракуем -------------------------------------- #

from sender.ai_letter import bez_dlinnogo_tire  # noqa: E402


def test_tire_menyaetsya_na_defis():
    assert bez_dlinnogo_tire("завод — крупный") == "завод - крупный"
    assert bez_dlinnogo_tire("завод—крупный") == "завод - крупный"
    assert bez_dlinnogo_tire("короткое – тоже") == "короткое - тоже"


def test_tire_ne_skleivaet_abzacy():
    """\\s съел бы перевод строки и слепил абзацы — берём только пробелы
    и табы своей строки."""
    было = "Первый абзац.\n\nВторой — с тире."
    стало = bez_dlinnogo_tire(было)
    assert стало == "Первый абзац.\n\nВторой - с тире."
    assert стало.count("\n") == было.count("\n")


def test_tire_bez_tire_nichego_ne_portit():
    т = "Обычный текст, дефис-другой, и всё."
    assert bez_dlinnogo_tire(т) == т


def test_tire_pustaya_stroka():
    assert bez_dlinnogo_tire(None) == ""
    assert bez_dlinnogo_tire("") == ""
