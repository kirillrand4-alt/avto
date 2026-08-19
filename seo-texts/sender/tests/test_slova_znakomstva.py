# -*- coding: utf-8 -*-
"""«Смотрел профиль» не должно повторяться слово в слово во всей партии.

Владелец 19.08: «мне не нравилось, что "смотрел профиль" сильно часто,
что-нибудь типа "изучал вашу компанию" и подобные».

Претензия НЕ к самому заходу: профиль мы действительно смотрим — в enrich.db
12 555 паспортов сайта и 6 774 страницы снятого текста, и письмо потом
сверяется с ними заслоном «цех не подтверждён сайтом». Претензия к тому, что
слова одни и те же. Поэтому это не новый заход, а формулировки ВНУТРИ него:
квота считает «Смотрел», «Изучал» и «Ознакомился» одной формой, и правильно.
"""
from collections import Counter

from sender.ai_letter import ZNAKOMSTVO, gen_prompt, load_facts

ФАКТЫ = load_facts(division="kc")


def _карточка(i):
    return {"mode": "GENERIC", "company_name": f"ООО «Тест {i}»",
            "activity": "мехобработка", "okved": "25.62", "extra": {}}


def test_formulirovok_neskolko():
    assert len(set(ZNAKOMSTVO)) >= 6, "мало вариантов, фраза снова приестся"
    assert "Смотрел профиль" in ZNAKOMSTVO, (
        "прежняя формулировка законна — она просто не должна быть одна")


def test_v_partii_slova_rashodyatsya():
    """На партии формулировки не должны сойтись в одну."""
    было = Counter(ZNAKOMSTVO[(0 + i * 3) % len(ZNAKOMSTVO)]
                   for i in range(24))
    assert len(было) == len(ZNAKOMSTVO), (
        f"ротация схлопнулась: {len(было)} формулировок из {len(ZNAKOMSTVO)}")
    assert max(было.values()) <= 24 // len(ZNAKOMSTVO) + 1


def test_promt_nazyvaet_formulirovku():
    """Просьба должна попасть в промпт письма, иначе её никто не увидит."""
    п = gen_prompt([_карточка(0)], ФАКТЫ, "kc", angle_base=0)
    assert "ЕСЛИ ГОВОРИШЬ, ЧТО СМОТРЕЛ ИХ" in п
    assert any(ф in п for ф in ZNAKOMSTVO)


def test_raznye_pisma_raznye_slova():
    """Два письма подряд не должны получить одну формулировку."""
    a = gen_prompt([_карточка(0)], ФАКТЫ, "kc", angle_base=0)
    b = gen_prompt([_карточка(1)], ФАКТЫ, "kc", angle_base=1)
    из_a = [ф for ф in ZNAKOMSTVO if f"«{ф}…»" in a]
    из_b = [ф for ф in ZNAKOMSTVO if f"«{ф}…»" in b]
    assert из_a and из_b
    assert из_a != из_b, "соседним письмам досталась одна формулировка"
