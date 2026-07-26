# -*- coding: utf-8 -*-
"""#59: ротация ящиков — следующая отправка идёт со следующего ящика по кругу,
а не с первого по алфавиту при равной загрузке."""

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ""))
)
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.sender import Sender  # noqa: E402

BOXES = ["box-a@x.ru", "box-b@x.ru", "box-c@x.ru"]


def _make(last_sent):
    s = Sender.__new__(Sender)
    s.config = SimpleNamespace(
        provider_pools=lambda: {"pool": list(BOXES)},
        get=lambda k, d=None: d,
    )
    s._route_pool = lambda rcp, camp: "pool"
    s.division_block = lambda rcp, mid: None
    s.can_send_now = lambda mid, *, now, manual=False, force=False: True
    s._day_key = lambda now: "d"
    s.store = SimpleNamespace(
        get_mailbox_state=lambda mid: None,          # у всех загрузка 0
        last_sent_mailbox=lambda: last_sent,
    )
    return s


def test_rotation_picks_next_after_last():
    s = _make("box-a@x.ru")
    got = s.pick_mailbox(SimpleNamespace(), SimpleNamespace(),
                         now=datetime.now(timezone.utc))
    assert got == "box-b@x.ru"


def test_rotation_wraps_around():
    s = _make("box-c@x.ru")
    got = s.pick_mailbox(SimpleNamespace(), SimpleNamespace(),
                         now=datetime.now(timezone.utc))
    assert got == "box-a@x.ru"


def test_rotation_skips_unavailable():
    s = _make("box-a@x.ru")
    s.can_send_now = lambda mid, *, now, manual=False, force=False: mid != "box-b@x.ru"
    got = s.pick_mailbox(SimpleNamespace(), SimpleNamespace(),
                         now=datetime.now(timezone.utc))
    assert got == "box-c@x.ru"


def test_no_history_falls_back_to_least_loaded():
    s = _make(None)
    got = s.pick_mailbox(SimpleNamespace(), SimpleNamespace(),
                         now=datetime.now(timezone.utc))
    assert got == "box-a@x.ru"   # прежнее поведение: стабильно по загрузке
