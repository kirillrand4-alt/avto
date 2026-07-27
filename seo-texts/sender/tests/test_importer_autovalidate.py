# -*- coding: utf-8 -*-
"""Авто-валидация при заливке: unknown-получатели валидируются без ручного
запуска (просьба владельца 27.07)."""
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.dtos import RecipientIn  # noqa: E402
from sender.importer import auto_validate_once  # noqa: E402
from sender.store import Store  # noqa: E402


class _Cfg:
    def get(self, k, d=None):
        return d


def test_auto_validate_runs_only_when_unknown_exist(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.init_schema()
    calls = []

    def фейк(st, cfg, *, limit):
        calls.append(limit)
        return {"total": 1}

    # пустая база — валидатор не дёргается вовсе (и не ходит в DNS)
    assert auto_validate_once(store, _Cfg(), _validate=фейк) is None
    assert calls == []
    # появился unknown — валидатор вызван
    store.upsert_recipient(RecipientIn(
        email="x@zavod.ru", domain="zavod.ru", inn="1", company_name="З"))
    res = auto_validate_once(store, _Cfg(), _validate=фейк)
    assert res == {"total": 1} and calls == [300]
    store.close()
