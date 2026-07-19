"""Тесты LeadDesk (BUILD-NEW эпицентр): очередь лидов, взятие с оптимистичной
блокировкой (двойной захват невозможен), переходы статуса, SLA.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import Store, RecipientIn  # noqa: E402
from sender.leaddesk import LeadDesk, LeadConflict  # noqa: E402
from sender.errors import ValidationError  # noqa: E402


class _Cfg:
    def __init__(self, data=None):
        self._d = data or {}

    def get(self, k, d=None):
        return self._d.get(k, d)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "ld.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def desk(store):
    return LeadDesk(_Cfg(), store)


@pytest.fixture
def mgr(store):
    return store.create_user(username="m", password_hash="p")


@pytest.fixture
def mgr2(store):
    return store.create_user(username="m2", password_hash="p")


@pytest.fixture
def recipient(store):
    rid = store.upsert_recipient(RecipientIn(
        email="lead@x.ru", domain="x.ru", company_name="Альфа Пром", inn="7701"))
    return SimpleNamespace(id=rid, email="lead@x.ru", company_name="Альфа Пром", inn="7701")


class _FakeBitrix:
    def __init__(self):
        self.calls = []

    def push_warm_lead(self, recipient, thread_id, snippet):
        self.calls.append((recipient.email, thread_id))
        return 555  # bitrix_lead_id


# ---- push_warm_lead (вход из imap) ----

def test_push_parses_tags(desk, recipient):
    lid = desk.push_warm_lead(recipient, "thread-1",
                              "[hot, тел +79001234567] Пришлите КП на компрессор")
    lead = desk.get(lid)
    assert lead.reply_kind == "hot"
    assert lead.phone == "+79001234567"
    assert "Пришлите КП" in lead.need
    assert lead.sla_due_at is not None
    assert lead.company_name == "Альфа Пром"


def test_push_idempotent_by_thread(desk, recipient):
    a = desk.push_warm_lead(recipient, "t1", "первый")
    b = desk.push_warm_lead(recipient, "t1", "повтор")
    assert a == b
    assert desk.stats()["total"] == 1


def test_push_without_thread_dedups_by_email(desk, recipient):
    a = desk.push_warm_lead(recipient, "", "x")
    b = desk.push_warm_lead(recipient, "", "y")
    assert a == b


def test_push_chains_to_bitrix(store, recipient):
    bx = _FakeBitrix()
    desk = LeadDesk(_Cfg(), store, bitrix_sink=bx)
    lid = desk.push_warm_lead(recipient, "t1", "нужен компрессор")
    assert bx.calls == [("lead@x.ru", "t1")]
    assert desk.get(lid).bitrix_lead_id == 555
    # повторный push (дедуп) не дёргает Bitrix снова
    desk.push_warm_lead(recipient, "t1", "повтор")
    assert len(bx.calls) == 1


# ---- take: оптимистичная блокировка ----

def test_take_success(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    lead = desk.take(lid, user_id=mgr)
    assert lead.status == "taken" and lead.assigned_to == mgr


def test_double_take_blocked(desk, recipient, mgr, mgr2):
    """Второй менеджер не может взять уже взятый лид."""
    lid = desk.push_warm_lead(recipient, "t1", "x")
    desk.take(lid, user_id=mgr)
    with pytest.raises(ValidationError):
        desk.take(lid, user_id=mgr2)


def test_concurrent_take_one_wins(store, recipient, mgr, mgr2):
    """Гонка на уровне версий: одна из двух попыток CAS с одинаковой версией
    проваливается (LeadConflict в реальной гонке)."""
    desk = LeadDesk(_Cfg(), store)
    lid = desk.push_warm_lead(recipient, "t1", "x")
    lead = desk.get(lid)
    # эмулируем: оба прочитали version=0, оба пытаются взять
    r1 = store.update_lead_cas(lid, expected_version=lead.version, status="taken", assigned_to=mgr)
    r2 = store.update_lead_cas(lid, expected_version=lead.version, status="taken", assigned_to=mgr2)
    assert r1 is not None and r2 is None  # второй — конфликт версий
    assert store.get_lead(lid).assigned_to == mgr


# ---- статус-переходы ----

def test_valid_transitions(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    desk.take(lid, user_id=mgr)
    lead = desk.set_status(lid, status="qualified", user_id=mgr)
    assert lead.status == "qualified"
    closed = desk.set_status(lid, status="closed", user_id=mgr)
    assert closed.status == "closed"


def test_illegal_transition_rejected(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    desk.take(lid, user_id=mgr)
    desk.set_status(lid, status="qualified", user_id=mgr)
    with pytest.raises(ValidationError):
        desk.set_status(lid, status="new", user_id=mgr)  # qualified -> new запрещён


def test_unknown_status_rejected(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    with pytest.raises(ValidationError):
        desk.set_status(lid, status="magic", user_id=mgr)


def test_assign_then_take(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    desk.assign(lid, manager_id=mgr)
    assert desk.get(lid).status == "assigned" and desk.get(lid).assigned_to == mgr
    desk.take(lid, user_id=mgr)
    assert desk.get(lid).status == "taken"


# ---- очередь/история ----

def test_queue_filters(desk, recipient, store, mgr):
    l1 = desk.push_warm_lead(recipient, "t1", "[hot] x")
    r2 = SimpleNamespace(id=store.upsert_recipient(RecipientIn(email="b@x.ru", domain="x.ru")),
                         email="b@x.ru", company_name=None, inn=None)
    l2 = desk.push_warm_lead(r2, "t2", "[interested] y")
    desk.take(l2, user_id=mgr)
    assert len(desk.queue()) == 2
    assert len(desk.queue(status="new")) == 1
    assert len(desk.queue(unassigned=True)) == 1
    assert len(desk.queue(assigned_to=mgr)) == 1
    assert len(desk.queue(reply_kind="hot")) == 1


def test_history_records_actions(desk, recipient, mgr):
    lid = desk.push_warm_lead(recipient, "t1", "x")
    desk.take(lid, user_id=mgr)
    actions = [e["action"] for e in desk.history(lid)]
    assert actions == ["created", "taken"]


def test_take_missing_lead(desk):
    with pytest.raises(ValidationError):
        desk.take(99999, user_id=1)
