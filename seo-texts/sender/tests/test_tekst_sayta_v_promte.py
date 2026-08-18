# -*- coding: utf-8 -*-
"""Текст сайта обязан попадать в промпт письма, а не только в рецензию.

18.08. Рецензент забраковал 413 писем из 1119, и почти все претензии одного
вида: письмо называет процесс, которого на сайте нет. Карточка «производство
каркасно-тентовых ангаров» превращалась в «сварку металлокаркаса, раскрой
тентовой ткани ПВХ и пневмоинструмент на сборке».

Паспорт сайта (списки продукции и линий) до промпта доезжал — это проверено
отдельно. Но заполненность паспорта у годных и бракованных писем ОДИНАКОВА
(оборудование_линии: 60% и 60%), значит дело не в нехватке данных: модели
было нечем себя проверить. Текст сайта — тот же, что читает рецензент, —
закрывает именно это.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender import ai_letter  # noqa: E402

САЙТ = ("Компания «Алтай-Тент» производит каркасно-тентовые ангары и склады. "
        "Собственный цех металлообработки, участок раскроя тента.")


def _собрать(**extra):
    """Блок получателя — та часть промпта, куда кладутся его факты."""
    rec = {"company_name": 'ООО "Алтай-Тент"', "inn": "2222000000",
           "email": "info@altai-tent.ru", "okved": "25.11",
           "extra": dict(extra)}
    return ai_letter._recipient_block(0, rec, "kc")


def test_tekst_sayta_popadaet_v_promt():
    т = _собрать(site_text=САЙТ)
    assert "участок раскроя тента" in т, т[-1500:]
    assert "ТЕКСТ ИХ САЙТА" in т


def test_pravilo_pro_processy_ryadom_s_tekstom():
    т = _собрать(site_text=САЙТ)
    assert "ЖЁСТКОЕ ПРАВИЛО ПО ЭТОМУ ТЕКСТУ" in т
    for слово in ("покраска", "дробеструй", "пневмоинструмент"):
        assert слово in т, слово


def test_bez_teksta_promt_ne_lomaetsya():
    т = _собрать()
    assert "ТЕКСТ ИХ САЙТА" not in т
    assert len(т) > 200


def test_dlinnyy_sayt_obrezaetsya():
    т = _собрать(site_text="а" * 9000)
    assert "а" * 3500 in т
    assert "а" * 3600 not in т


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
