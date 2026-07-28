# -*- coding: utf-8 -*-
"""Фильтр направления в очереди подтверждений считается НА СЕРВЕРЕ и ДО
нарезки страницы.

Владелец 28.07: выбран Meyer, слева «11 из 50». Фильтр жил на фронте —
панель просила 50 писем, отбрасывала чужие у себя и показывала огрызок.
Тесты ниже падают на такой реализации: они просят страницу заведомо меньше
числа подходящих писем и проверяют, что в неё попали ИМЕННО подходящие."""

import inspect
import os
import sys
from types import SimpleNamespace

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def _строка(rid: int, division: str) -> dict:
    return {"id": rid, "email": f"a{rid}@x.ru", "inn": str(rid),
            "panel": {"company": {"division": division}}}


# Порядок постановки важен: первые два письма — чужого направления, поэтому
# наивная реализация (взять страницу, потом отфильтровать) вернёт пусто.
СТРОКИ = [
    _строка(1, "kc"),
    _строка(2, "kc"),
    _строка(3, "meyer"),
    _строка(4, "kc"),
    _строка(5, "kc+meyer"),   # оба направления — попадает в оба фильтра
    _строка(6, ""),           # без направления — видно всем
]


def _клиент():
    from fastapi.testclient import TestClient
    from sender.api.app import make_app, Principal

    class _Confirm:
        live = False

        def pending(self, **kw):
            return [dict(r) for r in СТРОКИ]

        def counts(self):
            return {"pending": len(СТРОКИ)}

        def send_as(self, r):
            return {"mailbox_id": None, "options": [], "from_name": ""}

    class _Auth:
        def resolve(self, t):
            f = list(inspect.signature(Principal).parameters)
            v = {"user_id": 1, "username": "t", "role": "owner", "id": 1,
                 "is_active": True, "session_id": 1, "token": "x"}
            return Principal(**{k: v.get(k, "owner") for k in f})

    deps = SimpleNamespace(
        confirm=_Confirm(), auth=_Auth(), config=SimpleNamespace(),
        store=SimpleNamespace(sent_flags=lambda **kw: {},
                              get_campaign=lambda cid: None))
    return TestClient(make_app(deps), raise_server_exceptions=False)


def _взять(c, query: str) -> dict:
    got = c.get("/confirm/queue" + query, headers={"Authorization": "Bearer x"})
    assert got.status_code == 200, got.text
    return got.json()


def test_meyer_набирает_страницу_из_своих():
    """limit=2 при трёх подходящих письмах: страница из ДВУХ meyer-писем."""
    d = _взять(_клиент(), "?order=id&limit=2&division=meyer")
    assert [r["id"] for r in d["pending"]] == [3, 5]
    # всего под фильтром: meyer + kc+meyer + без направления
    assert d["total"] == 3


def test_kc_видит_свои_и_нейтральные():
    d = _взять(_клиент(), "?order=id&limit=10&division=kc")
    assert [r["id"] for r in d["pending"]] == [1, 2, 4, 5, 6]
    assert d["total"] == 5


def test_без_фильтра_очередь_не_режется():
    d = _взять(_клиент(), "?order=id&limit=10")
    assert [r["id"] for r in d["pending"]] == [1, 2, 3, 4, 5, 6]
    # без фильтра полный набор не считается — панель откатится на counts
    assert d["total"] is None


def test_все_равносильно_отсутствию_фильтра():
    d = _взять(_клиент(), "?order=id&limit=10&division=все")
    assert [r["id"] for r in d["pending"]] == [1, 2, 3, 4, 5, 6]


def test_фильтр_не_ломает_сортировку_по_баллу():
    """Скоринг и фильтр должны работать вместе: сортируем весь pending,
    затем отбираем своих, и только потом режем страницу."""
    from fastapi.testclient import TestClient
    from sender.api.app import make_app, Principal

    строки = [
        {"id": 1, "email": "a@x.ru", "inn": "1",
         "panel": {"company": {"division": "kc"}, "scoring": {"score": 99}}},
        {"id": 2, "email": "b@x.ru", "inn": "2",
         "panel": {"company": {"division": "meyer"}, "scoring": {"score": 40}}},
        {"id": 3, "email": "c@x.ru", "inn": "3",
         "panel": {"company": {"division": "meyer"}, "scoring": {"score": 90}}},
    ]

    class _Confirm:
        live = False

        def pending(self, **kw):
            return [dict(r) for r in строки]

        def counts(self):
            return {"pending": len(строки)}

        def send_as(self, r):
            return {"mailbox_id": None, "options": [], "from_name": ""}

    class _Auth:
        def resolve(self, t):
            f = list(inspect.signature(Principal).parameters)
            v = {"user_id": 1, "username": "t", "role": "owner", "id": 1,
                 "is_active": True, "session_id": 1, "token": "x"}
            return Principal(**{k: v.get(k, "owner") for k in f})

    deps = SimpleNamespace(
        confirm=_Confirm(), auth=_Auth(), config=SimpleNamespace(),
        store=SimpleNamespace(sent_flags=lambda **kw: {},
                              get_campaign=lambda cid: None))
    c = TestClient(make_app(deps), raise_server_exceptions=False)
    d = _взять(c, "?limit=1&division=meyer")
    # самый горячий ИЗ MEYER, а не самый горячий вообще (тот kc с 99)
    assert [r["id"] for r in d["pending"]] == [3]
    assert d["total"] == 2
