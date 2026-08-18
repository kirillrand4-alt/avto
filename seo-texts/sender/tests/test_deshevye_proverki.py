# -*- coding: utf-8 -*-
"""Письмо пишет сильная модель, проверки читает модель попроще.

Замер 18.08: на одно готовое письмо приходится ~18 обращений к opus-4-8 и
$0.32. Творческий шаг там ровно один - написать письмо; судья, верификатор
и линза читают готовый текст по списку правил и отвечают «ok/не ok».
Владелец: «проверки, для них opus избыточен».

Здесь защищаются три вещи:
  * проверки идут ЧЕРЕЗ ДРУГОЙ вызыватель, а генерация — через основной;
  * без второго вызывателя поведение прежнее (всё одной моделью);
  * технолог и скептик спрашиваются ОДНИМ промптом, а не двумя.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import (AiLetterGen, _TEH_LENS_HEADS,  # noqa: E402
                              teh_lens_prompt)


def test_obe_linzy_odnim_promtom():
    п = teh_lens_prompt(
        [(1, 'ООО "Тест"', 'металлообработка', '25.11', 'Тема', 'Тело',
          'продукция: балки')], 'обе', 'kc')
    assert "ВЗГЛЯД ПЕРВЫЙ" in п and "ВЗГЛЯД ВТОРОЙ" in п
    assert "худший из двух" in п


def test_obe_est_u_oboih_napravleniy():
    for напр in ("kc", "meyer"):
        assert "обе" in _TEH_LENS_HEADS[напр], напр
        assert _TEH_LENS_HEADS[напр]["обе"].strip()


def test_proverki_idut_drugim_vyzyvatelem():
    зовы = {"письмо": 0, "проверка": 0}

    def письмо(prompt):
        зовы["письмо"] += 1
        return json.dumps({"letters": []})

    def проверка(prompt):
        зовы["проверка"] += 1
        return json.dumps({"verdicts": []})

    g = AiLetterGen(письмо, checker=проверка)
    g._ask("что угодно", "тест")
    g._ask("что угодно", "тест", checker=True)
    assert зовы == {"письмо": 1, "проверка": 1}, зовы


def test_bez_vtorogo_vyzyvatelya_povedenie_prezhnee():
    зовы = []

    def один(prompt):
        зовы.append(prompt)
        return json.dumps({"ok": True})

    g = AiLetterGen(один)
    g._ask("a", "t")
    g._ask("b", "t", checker=True)
    assert len(зовы) == 2, "оба вызова должны уйти в один и тот же вызыватель"


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:200]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
