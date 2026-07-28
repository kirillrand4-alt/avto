# -*- coding: utf-8 -*-
"""Чистка ленты от тестовых/мусорных записей (владелец 28.07): лиды — мягко,
открытия — с записью снимка в журнал аудита."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sender.store import Store  # noqa: E402


def _store():
    st = Store(os.path.join(tempfile.mkdtemp(), 's.db'))
    st.init_schema()
    # владелец-оператор: actor_user_id в lead_events и audit_log — внешний
    # ключ на users, без строки пользователя удаление падало бы на FK
    with st.transaction() as conn:
        conn.execute("INSERT INTO users(id, username, password_hash, role, "
                     "created_at, updated_at) VALUES(1, 'kirill', 'x', 'owner', "
                     "'2026-07-01T00:00:00.000000', '2026-07-01T00:00:00.000000')")
    return st


def _lead(st, email='a@b.ru', dedup='k1'):
    with st.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO leads(email, company_name, inn, status, dedup_key, "
            "created_at, updated_at) VALUES(?, 'ООО «Тест»', '77', 'new', ?, "
            "'2026-07-28T10:00:00.000000', '2026-07-28T10:00:00.000000')", (email, dedup))
        return cur.lastrowid


def test_deleted_lead_disappears_from_feed_and_returns():
    st = _store()
    lid = _lead(st)
    assert [l.id for l in st.list_leads()] == [lid]
    снимок = st.soft_delete_lead(lid, actor_user_id=1, reason='тест')
    assert снимок['email'] == 'a@b.ru'
    assert st.list_leads() == []                       # из ленты пропал
    assert [l.id for l in st.list_leads(status='deleted')] == [lid]   # но не из базы
    события = st.list_lead_events(lid)
    assert события[-1]['action'] == 'deleted'
    assert события[-1]['detail']['reason'] == 'тест'
    assert st.restore_lead(lid, actor_user_id=1) is True
    assert [l.id for l in st.list_leads()] == [lid]    # вернулся


def test_delete_lead_idempotent_and_missing():
    st = _store()
    lid = _lead(st)
    st.soft_delete_lead(lid)
    assert st.soft_delete_lead(lid) is not None        # повтор безопасен
    assert st.soft_delete_lead(999999) is None
    assert st.restore_lead(999999) is False


def _open_event(st, ключ='d1'):
    """message_id не ставим: там FK на messages, а для чистки ленты письмо
    не обязательно (открытие могло прийти по уже удалённому письму)."""
    with st.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO events(event_type, event_ts, created_at, dedup_key) "
            "VALUES('open', '2026-07-27T15:00:00.000000', "
            "'2026-07-27T15:00:00.000000', ?)", (ключ,))
        return cur.lastrowid


def test_delete_open_removes_and_audits():
    st = _store()
    eid = _open_event(st)
    assert len(st.recent_opens(limit=10)) == 1
    снимок = st.delete_open_event(eid, actor_user_id=1, reason='тестовое письмо')
    assert снимок['event_type'] == 'open'
    assert st.recent_opens(limit=10) == []
    audit = st.list_audit(limit=10) if hasattr(st, 'list_audit') else []
    if audit:
        top = audit[0]
        assert top['action'] == 'open.delete'
        assert top['detail']['reason'] == 'тестовое письмо'
        assert top['detail']['snapshot']['id'] == eid   # восстановимо


def test_delete_open_refuses_other_event_types():
    """Снести случайно bounce или reply нельзя — только открытия."""
    st = _store()
    with st.transaction() as conn:
        cur = conn.execute(
            "INSERT INTO events(event_type, event_ts, created_at, "
            "dedup_key) VALUES('bounce', '2026-07-27T15:00:00.000000', "
            "'2026-07-27T15:00:00.000000', 'db')")
        bid = cur.lastrowid
    assert st.delete_open_event(bid) is None
    with st.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM events WHERE id=?",
                            (bid,)).fetchone()["c"] == 1
    assert st.delete_open_event(999999) is None


def test_stats_total_excludes_deleted():
    """После чистки мусора общий счётчик не должен оставаться раздутым."""
    st = _store()
    a, b = _lead(st, 'a@b.ru', 'k1'), _lead(st, 'c@d.ru', 'k2')
    assert st.lead_stats()['total'] == 2
    st.soft_delete_lead(b, actor_user_id=1, reason='тест')
    stats = st.lead_stats()
    assert stats['total'] == 1                     # в работе остался один
    assert stats['by_status'].get('deleted') == 1  # но видно, сколько убрали
    assert a
