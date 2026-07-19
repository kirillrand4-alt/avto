"""Тесты BUILD-NEW store-методов (Фаза 2.1): lead-desk (CAS), auth, audit."""

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import Store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "ld.db"))
    s.init_schema()
    yield s
    s.close()


# ---- lead-desk ----

def test_create_lead_idempotent(store):
    lid, created = store.create_lead(email="a@x.ru", dedup_key="t1", reply_kind="hot")
    assert created is True
    lid2, created2 = store.create_lead(email="a@x.ru", dedup_key="t1")
    assert created2 is False and lid2 == lid
    # created-событие записано один раз
    assert [e["action"] for e in store.list_lead_events(lid)] == ["created"]


def test_take_lead_cas_success_and_conflict(store):
    lid, _ = store.create_lead(email="a@x.ru", dedup_key="t1")
    u = store.create_user(username="ivan", password_hash="ph")
    # успех при верной версии
    r = store.update_lead_cas(lid, expected_version=0, actor_user_id=u,
                              action="taken", status="taken", assigned_to=u)
    assert r is not None and r.status == "taken" and r.assigned_to == u
    assert r.version == 1
    # конфликт: та же старая версия
    conflict = store.update_lead_cas(lid, expected_version=0, status="qualified")
    assert conflict is None
    # успех при новой версии
    r2 = store.update_lead_cas(lid, expected_version=1, status="qualified")
    assert r2 is not None and r2.status == "qualified" and r2.version == 2


def test_update_lead_cas_missing(store):
    assert store.update_lead_cas(99999, expected_version=0, status="x") is None


def test_list_leads_filters(store):
    store.create_lead(email="a@x.ru", dedup_key="t1", reply_kind="hot")
    l2, _ = store.create_lead(email="b@x.ru", dedup_key="t2", reply_kind="interested")
    u = store.create_user(username="ivan", password_hash="ph")
    store.update_lead_cas(l2, expected_version=0, status="assigned", assigned_to=u)
    assert len(store.list_leads()) == 2
    assert len(store.list_leads(status="new")) == 1
    assert len(store.list_leads(unassigned=True)) == 1
    assert len(store.list_leads(assigned_to=u)) == 1
    assert len(store.list_leads(reply_kind="hot")) == 1


def test_lead_events_and_stats(store):
    lid, _ = store.create_lead(email="a@x.ru", dedup_key="t1")
    store.update_lead_cas(lid, expected_version=0, action="taken", status="taken")
    events = store.list_lead_events(lid)
    assert [e["action"] for e in events] == ["created", "taken"]
    assert events[1]["from_status"] == "new" and events[1]["to_status"] == "taken"
    stats = store.lead_stats()
    assert stats["total"] == 1 and stats["by_status"] == {"taken": 1}


def test_lead_sla_overdue(store):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    store.create_lead(email="a@x.ru", dedup_key="t1", sla_due_at=past)
    assert store.lead_stats()["sla_overdue"] == 1
    # взятый в работу лид больше не считается просроченным по SLA первого касания
    lid2, _ = store.create_lead(email="b@x.ru", dedup_key="t2", sla_due_at=past)
    store.update_lead_cas(lid2, expected_version=0, status="taken")
    assert store.lead_stats()["sla_overdue"] == 1  # только первый


# ---- auth ----

def test_user_crud(store):
    uid = store.create_user(username="ivan", password_hash="ph", role="owner", email="i@x.ru")
    u = store.get_user(uid)
    assert u.username == "ivan" and u.role == "owner" and u.is_active is True
    assert store.get_user_by_username("ivan").id == uid
    store.update_user(uid, role="manager", totp_secret="BASE32SECRET")
    u2 = store.get_user(uid)
    assert u2.role == "manager" and u2.totp_secret == "BASE32SECRET"
    assert len(store.list_users()) == 1


def test_sessions(store):
    uid = store.create_user(username="ivan", password_hash="ph")
    exp = datetime.now(timezone.utc) + timedelta(days=1)
    store.create_session(user_id=uid, token_hash="tok1", expires_at=exp)
    store.create_session(user_id=uid, token_hash="tok2", expires_at=exp)
    assert store.get_session_by_token("tok1").revoked is False
    store.revoke_session("tok1")
    assert store.get_session_by_token("tok1").revoked is True
    assert store.get_session_by_token("tok2").revoked is False
    store.revoke_user_sessions(uid)
    assert store.get_session_by_token("tok2").revoked is True


# ---- audit ----

def test_audit_log(store):
    uid = store.create_user(username="ivan", password_hash="ph")
    store.append_audit(action="login", actor_user_id=uid, ip="1.2.3.4")
    store.append_audit(action="campaign_activate", actor_user_id=uid,
                       entity_type="campaign", entity_id=5, detail={"name": "К1"})
    rows = store.list_audit()
    assert len(rows) == 2
    assert rows[0]["action"] == "campaign_activate"  # DESC
    assert rows[0]["detail"] == {"name": "К1"}
    assert len(store.list_audit(action="login")) == 1
    assert len(store.list_audit(actor_user_id=uid)) == 2
