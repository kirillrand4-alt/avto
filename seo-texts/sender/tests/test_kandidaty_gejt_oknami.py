# -*- coding: utf-8 -*-
"""Дорогой гейт судит окно, а не весь запас: кнопка не должна висеть 7 минут.

Замер 17.08 на боевой панели: candidates(10, 14) шла 403 секунды. Внутри
запас = limit*10 = 140 компаний, и на каждой без кэшированного вердикта гейт
рода деятельности зовёт провайдера двумя линзами (~2.9 с на компанию).
Владелец нажал кнопку, панель отвалилась по таймауту, и выглядело это как
«кнопка ничего не делает».

Отдаём мы limit штук, а сортировка по накалу уже прошла - значит судить надо
окно сверху и добирать следующим окном, только если гейт много вырезал.

Тесты держат ровно это: сколько компаний уходит в гейт и сколько писем
возвращается.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_quota import AiQuota  # noqa: E402


class _R:
    def __init__(self, i):
        self.id = i
        self.inn = str(1000000000 + i)
        self.email = f"a{i}@z{i}.ru"
        self.company_name = f"Фирма {i}"
        self.okved = "25.62"
        self.segment = "Партия 935"


def _квота(всего=200, не_покупатели=frozenset()):
    """Квота с подменёнными зависимостями: считаем вызовы дорогого гейта."""
    q = AiQuota.__new__(AiQuota)
    все = [_R(i) for i in range(всего)]
    q._судимые = []

    q._segment = lambda cid: "Партия 935"
    q._already = lambda cid: set()

    class _Store:
        def query_recipients(self, флаги, limit=0, offset=0):
            return все[offset:offset + limit]
    q._store = _Store()
    q._nontarget_inns = lambda inns: set()
    q._dead_addresses = lambda mails: set()
    q._hotness_map = lambda inns: {}

    def _nb(получатели):
        q._судимые.append(len(получатели))
        return {r.inn for r in получатели if r.inn in не_покупатели}
    q._not_buyers = _nb
    return q


def test_sudim_okno_a_ne_ves_zapas():
    """Главное: в гейт уходит окно 2*limit, а не запас 10*limit."""
    q = _квота()
    из = q.candidates(10, 14)
    assert len(из) == 14
    assert q._судимые == [28], q._судимые


def test_dobiraem_kogda_geyt_mnogo_vyrezal():
    """Если окно выкосили, берём следующее — писем всё равно limit."""
    отказники = {str(1000000000 + i) for i in range(0, 40)}
    q = _квота(не_покупатели=отказники)
    из = q.candidates(10, 5)
    assert len(из) == 5, len(из)
    assert len(q._судимые) >= 2, q._судимые
    assert all(r.inn not in отказники for r in из)


def test_ne_sudim_bolshe_chem_est():
    """Кандидатов меньше окна — судим их и не зацикливаемся."""
    q = _квота(всего=7)
    из = q.candidates(10, 14)
    assert len(из) == 7
    assert sum(q._судимые) == 7, q._судимые


def test_vse_otkazniki_pustoy_otvet_bez_zaviscaniya():
    отказники = {str(1000000000 + i) for i in range(200)}
    q = _квота(не_покупатели=отказники)
    assert q.candidates(10, 10) == []
    # прошли весь запас (limit*10=100) окнами по 20 и остановились
    assert sum(q._судимые) == 100, q._судимые


def test_nulevoy_limit_v_geyt_ne_hodit():
    q = _квота()
    assert q.candidates(10, 0) == []
    assert q._судимые == []


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:120]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
