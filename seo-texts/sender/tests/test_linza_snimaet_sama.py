"""Линза отказала дважды — письмо снимается само (решение владельца 19.08).

Выросло из перезаписи мейеровских групп: три письма не выходили с трёх
попыток, и каждый раз линза говорила одно и то же — «по сайту это
консультации», «продажа швейного оборудования», «торгует металлопрокатом со
склада». Но её вердикт лишь ронял генерацию, а СТАРОЕ письмо про пищевую
сортировку оставалось в очереди и ушло бы, подтверди его оператор.

Проверяю поведение:
  * первый отказ линзы письмо НЕ снимает (линза ошибается на нетипичных
    профилях — «Чистай Агроторг» 14.08);
  * второй снимает;
  * отказ НЕ про профиль (объём, дубль слова) не считается вовсе, сколько
    бы раз ни повторился;
  * одобренное письмо гасится через messages, раз решение не перерешать.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.ai_quota import AiQuota  # noqa: E402


class _Соединение:
    def __init__(self):
        self.строки = []

    def execute(self, sql, args=()):
        s = sql.strip().lower()
        if s.startswith("insert into linza_otkazy"):
            self.строки.append(args)
        elif s.startswith("select count(*) from linza_otkazy"):
            n = sum(1 for a in self.строки if a[0] == args[0])
            return _Курсор(n)
        return _Курсор(0)

    def commit(self):
        pass


class _Курсор:
    def __init__(self, n):
        self._n = n

    def fetchone(self):
        return (self._n,)


class _Замок:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Стор:
    def __init__(self, decide=True):
        self._conn = _Соединение()
        self._lock = _Замок()
        self.решения = []
        self.погашено = []
        self._decide = decide

    def confirm_decide(self, rid, **kw):
        self.решения.append((rid, kw.get("status")))
        return self._decide

    def confirm_get(self, rid):
        return {"message_id": 555}

    def mark_skipped(self, mid, reason):
        self.погашено.append((mid, reason))


def _квота(стор):
    q = AiQuota.__new__(AiQuota)
    q._store = стор
    return q


ЛИНЗА = ["инженерная линза после починки: по сайту это консультации"]
НЕ_ЛИНЗА = ["объём 147 слов (норма 45-140)"]


def test_pervyy_otkaz_ne_snimaet():
    с = _Стор()
    q = _квота(с)
    assert q._snyat_esli_ne_nash(10, ЛИНЗА) is False
    assert с.решения == []


def test_vtoroy_otkaz_snimaet():
    с = _Стор()
    q = _квота(с)
    q._snyat_esli_ne_nash(10, ЛИНЗА)
    assert q._snyat_esli_ne_nash(10, ЛИНЗА) is True
    assert с.решения == [(10, "skipped")]


def test_ne_pro_profil_ne_schitaetsya():
    с = _Стор()
    q = _квота(с)
    for _ in range(4):
        assert q._snyat_esli_ne_nash(11, НЕ_ЛИНЗА) is False
    assert с.решения == [] and с._conn.строки == []


def test_odobrennoe_gasitsya_pismom():
    """confirm_decide вернул False — значит письмо уже одобрено."""
    с = _Стор(decide=False)
    q = _квота(с)
    q._snyat_esli_ne_nash(12, ЛИНЗА)
    assert q._snyat_esli_ne_nash(12, ЛИНЗА) is True
    assert с.погашено and с.погашено[0][0] == 555


def test_schyot_po_svoemu_pismu():
    """Отказы по одному письму не снимают соседнее."""
    с = _Стор()
    q = _квота(с)
    q._snyat_esli_ne_nash(20, ЛИНЗА)
    assert q._snyat_esli_ne_nash(21, ЛИНЗА) is False
