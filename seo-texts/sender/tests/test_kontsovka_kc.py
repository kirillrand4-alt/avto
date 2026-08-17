# -*- coding: utf-8 -*-
"""Строка отказа: у КЦ она в каноне, у Meyer снята.

Решение 14.08 («редактор вычеркнула, в конце оставить один вопрос») сняло
строку ВЕЗДЕ, а относилось оно к Meyer — уточнение владельца 17.08.

Замер, из-за которого это всплыло: в согласованной кампании 5
«Металлообработка 25.x» строка стоит в 207 письмах из 275 (75%), а во всех
140 письмах партии 935 КЦ её нет вовсе. На письма со строкой приходили
ответы.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import KONTSOVKA, zashit_kontsovku  # noqa: E402

БЕЗ_ОТКАЗА = (
    "Добрый день!\n\n"
    "Смотрел профиль «Миан» - крупногабаритные металлоконструкции.\n\n"
    "Я веду направление компрессорного оборудования в Компрессор Центре. "
    "Подскажите, актуален ли для вас вопрос обновления парка?\n\n"
    "С уважением,")
СО_СТАРЫМ = (
    "Добрый день!\n\n"
    "Смотрел профиль «Миан».\n\n"
    "Извините за письмо, больше не побеспокою.\n\n"
    "С уважением,")


def test_kc_dopisyvaet_stroku_otkaza():
    """Строки нет — у КЦ она обязана появиться, и перед «С уважением»."""
    стало = zashit_kontsovku(БЕЗ_ОТКАЗА, "kc")
    assert KONTSOVKA in стало, стало
    assert стало.index(KONTSOVKA) < стало.index("С уважением"), стало


def test_meyer_stroku_ne_dopisyvaet():
    """У Meyer поведение прежнее: строки не было — не появилась."""
    стало = zashit_kontsovku(БЕЗ_ОТКАЗА, "meyer")
    assert KONTSOVKA not in стало, стало


def test_umolchanie_vedyot_sebya_kak_ranshe():
    """Вызов без направления не меняет поведения молча.

    Умолчание 'meyer' выбрано именно за это: старые вызывающие, которые
    направление не передают, продолжают вырезать строку, как и вырезали.
    """
    assert zashit_kontsovku(БЕЗ_ОТКАЗА) == zashit_kontsovku(БЕЗ_ОТКАЗА, "meyer")


def test_kc_zamenyaet_staruyu_formulirovku():
    """Старое извинение у КЦ заменяется каноном, а не соседствует с ним."""
    стало = zashit_kontsovku(СО_СТАРЫМ, "kc")
    assert KONTSOVKA in стало, стало
    assert "не побеспокою" not in стало, стало


def test_meyer_staruyu_vyrezaet():
    """У Meyer старая формулировка по-прежнему вырезается начисто."""
    стало = zashit_kontsovku(СО_СТАРЫМ, "meyer")
    assert "не побеспокою" not in стало, стало
    assert KONTSOVKA not in стало, стало


def test_idempotentno():
    """Второй прогон ничего не добавляет: строка ровно одна."""
    один = zashit_kontsovku(БЕЗ_ОТКАЗА, "kc")
    два = zashit_kontsovku(один, "kc")
    assert один == два, (один, два)
    assert два.count(KONTSOVKA) == 1, два


def test_bez_finala_stroka_vsyo_ravno_est():
    """«С уважением» может не быть — строка всё равно должна появиться."""
    стало = zashit_kontsovku("Добрый день!\n\nКороткое письмо.", "kc")
    assert KONTSOVKA in стало, стало


def test_vopros_v_stroke_ne_teryaetsya():
    """Отказ, слепленный с единственным вопросом, не уносим вместе с ним."""
    слепленное = ("Добрый день!\n\nПодскажите, актуально ли, а если нет - "
                  "буду признателен за короткий ответ?\n\nС уважением,")
    стало = zashit_kontsovku(слепленное, "kc")
    assert "актуально ли" in стало, стало


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {ex}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
