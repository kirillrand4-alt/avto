# -*- coding: utf-8 -*-
"""Параллельная генерация (решение владельца 27.07): все письма доходят до
очереди, счётчики не теряются на гонках, порядок значения не имеет."""
import os
import sys
import threading

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_quota import AiQuota  # noqa: E402


class _Cfg:
    def __init__(self, workers):
        self._w = workers

    def get(self, k, d=None):
        return self._w if k == "ai_quota.workers" else d


class _Res:
    def __init__(self):
        self.ok = {}
        self.rejected = {}


class _Gen:
    """Фейковый генератор: письмо каждому, с задержкой — чтобы потоки реально
    пересеклись и гонка счётчиков всплыла бы, если бы лока не было."""

    def generate(self, reqs):
        r = _Res()
        for i, q in enumerate(reqs):
            r.ok[i] = {"subject": f"т{q['company_name']}", "body": "тело",
                       "rounds": []}
        return r


def _quota(workers, письма):
    q = AiQuota.__new__(AiQuota)
    q._config = _Cfg(workers)
    q._batch = 4
    q._gen_factory = lambda: _Gen()
    q._request = lambda r: {"company_name": r.company_name, "extra": {}}
    q._add_ideas_generic = lambda reqs: None
    q._panel = lambda *a, **kw: {}
    q._ensure_message = lambda cid, rid: (rid, 1, "")
    q._log = lambda *a, **kw: None
    сложено = []
    замок = threading.Lock()

    class _S:
        def confirm_submit(self, **kw):
            with замок:
                сложено.append(kw["email"])
    q._store = _S()
    return q, сложено


class _R:
    def __init__(self, i):
        self.id = i
        self.email = f"a{i}@z.ru"
        self.inn = str(1000000000 + i)
        self.company_name = f"К{i}"


def test_parallel_generates_every_letter():
    q, сложено = _quota(15, 37)
    q.today = lambda: "2026-07-27"
    q.schedule = lambda cid: {"2026-07-27": 100}
    q.counters = lambda cid, days: {"2026-07-27": (0, 0)}
    q.candidates = lambda cid, n: [_R(i) for i in range(37)]
    res = q.run_today(1)
    assert res.generated == 37
    assert len(сложено) == 37 and len(set(сложено)) == 37


def test_single_worker_same_result():
    q, сложено = _quota(1, 9)
    q.today = lambda: "2026-07-27"
    q.schedule = lambda cid: {"2026-07-27": 100}
    q.counters = lambda cid, days: {"2026-07-27": (0, 0)}
    q.candidates = lambda cid, n: [_R(i) for i in range(9)]
    res = q.run_today(1)
    assert res.generated == 9 and len(сложено) == 9
