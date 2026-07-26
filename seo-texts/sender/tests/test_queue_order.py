# -*- coding: utf-8 -*-
"""#70: очередь подтверждений отдаётся в порядке скоринга — горячие сверху."""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


def test_queue_sorted_by_score(monkeypatch):
    import inspect
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from sender.api.app import make_app, Principal

    rows = [
        {"id": 1, "email": "a@x.ru", "inn": "1", "panel": {"scoring": {"score": 45}}},
        {"id": 2, "email": "b@x.ru", "inn": "2", "panel": {"scoring": {"score": 74}}},
        {"id": 3, "email": "c@x.ru", "inn": "3", "panel": {}},   # без балла — вниз
        {"id": 4, "email": "d@x.ru", "inn": "4", "panel": {"scoring": {"score": 74}}},
    ]

    class _Confirm:
        live = False

        def pending(self, **kw):
            return [dict(r) for r in rows]

        def counts(self):
            return {"pending": len(rows)}

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
    got = c.get("/confirm/queue", headers={"Authorization": "Bearer x"})
    assert got.status_code == 200
    ids = [r["id"] for r in got.json()["pending"]]
    # 74 и 74 (ничья по постановке), потом 45, письмо без балла — последним
    assert ids == [2, 4, 1, 3]
    # порядок постановки по требованию сохраняется
    got2 = c.get("/confirm/queue?order=id", headers={"Authorization": "Bearer x"})
    assert [r["id"] for r in got2.json()["pending"]] == [1, 2, 3, 4]
