# -*- coding: utf-8 -*-
"""Антиштамп помнит заходы уже сделанных писем кампании.

zahod_overflow считает квоту по списку одного вызова generate(). В панели
пачка по 4 письма, и каждая начинается с чистого счётчика; серверный прогон
партии подаёт по одному письму — там квота не срабатывает никогда (предел
max(1, int(1*0.34)) = 1, счётчик формы = 1, «больше предела» не наступает).

Замер 17.08 по GENERIC-письмам: кампания 9 «Богатые карточки» — верхняя
форма 26% (квота цела), кампания 10 «Партия 935 — КЦ» — 87% (квота мертва).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import zahod_overflow, форма_захода  # noqa: E402
from sender.ai_quota import AiQuota  # noqa: E402

ПРОФИЛЬ = ("Добрый день!\n\nСмотрел профиль «{}» - завод.\n\n"
           "Подскажите, актуально?\n\nС уважением,")
ПЛОЩАДКА = ("Добрый день!\n\nНа площадке «{}» сжатый воздух нужен везде.\n\n"
            "Подскажите, актуально?\n\nС уважением,")


class _Store:
    """Очередь-заглушка: отдаёт тела писем кампании."""

    def __init__(self, тела):
        self._тела = тела

    def confirm_list(self, campaign_id=None, limit=None):
        return [{"body": т, "edited_body": None} for т in self._тела]


def _кво(тела):
    q = AiQuota.__new__(AiQuota)          # без конструктора: нужен только store
    q._store = _Store(тела)
    return q


def test_kvota_mertva_na_odnom_pisme():
    """Опора всей правки: в бою письмо подаётся по одному, и квота молчит."""
    assert zahod_overflow([ПРОФИЛЬ.format("A")]) == {}
    assert len(zahod_overflow([ПРОФИЛЬ.format(c) for c in "AB"])) == 1


def test_pamyat_lovit_pereborschika():
    """Восемь писем одной формой — форма названа перебравшей."""
    q = _кво([ПРОФИЛЬ.format(c) for c in "ABCDEFGH"])
    assert q._izbytochnyy_zahod(10) == форма_захода(ПРОФИЛЬ.format("A"))


def test_pamyat_molchit_kogda_raznoobrazno():
    """Ровно пополам — квота 34% перебрана... а вот и нет: 50% > 34%.

    Поэтому берём разнообразие ПОШИРЕ: одна форма из трёх писем восьми не
    перебирает треть.
    """
    тела = ([ПРОФИЛЬ.format(c) for c in "AB"]
            + [ПЛОЩАДКА.format(c) for c in "CDEF"])
    q = _кво(тела)
    верх = q._izbytochnyy_zahod(10)
    # «от площадки» 4 из 6 — перебор; «от профиля» 2 из 6 — нет
    assert верх == форма_захода(ПЛОЩАДКА.format("C")), верх


def test_malo_pisem_ne_povod():
    """На двух письмах доля ничего не значит — молчим."""
    q = _кво([ПРОФИЛЬ.format(c) for c in "AB"])
    assert q._izbytochnyy_zahod(10) == ""


def test_pustaya_kampaniya():
    assert _кво([])._izbytochnyy_zahod(10) == ""


def test_bez_kampanii_ne_hodim_v_bazu():
    """campaign_id нет — подсказки нет, и очередь не читается."""
    class _Взрыв:
        def confirm_list(self, **_):
            raise AssertionError("очередь читаться не должна")
    q = AiQuota.__new__(AiQuota)
    q._store = _Взрыв()
    assert q._izbytochnyy_zahod(None) == ""


def test_sboy_ocheredi_ne_ronyaet_generaciyu():
    """Очередь упала — возвращаем пустое, а не исключение."""
    class _Сбой:
        def confirm_list(self, **_):
            raise RuntimeError("database is locked")
    q = AiQuota.__new__(AiQuota)
    q._store = _Сбой()
    assert q._izbytochnyy_zahod(10) == ""


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
