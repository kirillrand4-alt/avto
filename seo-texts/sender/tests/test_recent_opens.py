# -*- coding: utf-8 -*-
"""Последние открытия с привязкой к письму (владелец 28.07: «нужно видеть,
какое именно письмо было открыто», а не только общий счётчик)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sender.store import Store  # noqa: E402


def _store():
    st = Store(os.path.join(tempfile.mkdtemp(), 's.db'))
    st.init_schema()
    return st


def _seed(st):
    """Минимальный набор: получатель -> кампания -> шаг -> письмо."""
    with st.transaction() as conn:
        conn.execute("INSERT INTO recipients(id, inn, email, domain, company_name, "
                     "created_at, updated_at) VALUES(7, '123', 'zakup@zavod.ru', "
                     "'zavod.ru', 'ООО «Завод»', '2026-07-01T00:00:00', "
                     "'2026-07-01T00:00:00')")
        conn.execute("INSERT INTO campaigns(id, name, status, legal_entity, "
                     "legal_inn, created_at, updated_at) VALUES(1, 'c', 'active', "
                     "'ООО «Руспром»', '2221239841', '2026-07-01T00:00:00', "
                     "'2026-07-01T00:00:00')")
        conn.execute("INSERT INTO sequence_steps(id, campaign_id, step_index, "
                     "delay_hours, subject_tmpl, body_tmpl, created_at) "
                     "VALUES(1, 1, 0, 0, 's', 'b', '2026-07-01T00:00:00')")
        conn.execute(
            "INSERT INTO messages(id, idempotency_key, campaign_id, recipient_id, "
            "sequence_step_id, mailbox_id, status, subject, sent_at, "
            "created_at, updated_at) "
            "VALUES(55, 'k1', 1, 7, 1, 'k.yashin@kompressor-expert.ru', 'sent', "
            "'Вопрос по компрессорному парку', '2026-07-27T10:00:00', "
            "'2026-07-27T09:00:00', '2026-07-27T10:00:00')")


def test_recent_opens_joins_letter_and_company():
    st = _store()
    _seed(st)
    with st.transaction() as conn:
        conn.execute("INSERT INTO events(event_type, message_id, recipient_id, "
                     "event_ts, created_at, dedup_key) VALUES('open', 55, 7, "
                     "'2026-07-27T15:03:20', '2026-07-27T15:03:20', 'd1')")
    rows = st.recent_opens(limit=10)
    assert len(rows) == 1
    r = rows[0]
    assert r['subject'] == 'Вопрос по компрессорному парку'
    assert r['company'] == 'ООО «Завод»' and r['email'] == 'zakup@zavod.ru'
    assert r['mailbox_id'] == 'k.yashin@kompressor-expert.ru'
    assert r['message_id'] == 55 and r['inn'] == '123'


def test_recipient_resolved_from_message_when_event_has_none():
    """У части событий recipient_id пуст — тянем его через письмо."""
    st = _store()
    _seed(st)
    with st.transaction() as conn:
        conn.execute("INSERT INTO events(event_type, message_id, event_ts, "
                     "created_at, dedup_key) VALUES('open', 55, "
                     "'2026-07-27T15:04:00', '2026-07-27T15:04:00', 'd2')")
    r = st.recent_opens(limit=10)[0]
    assert r['company'] == 'ООО «Завод»' and r['recipient_id'] == 7


def test_order_and_limit_and_other_events_ignored():
    st = _store()
    _seed(st)
    with st.transaction() as conn:
        for ts in ('2026-07-01T10:00:00', '2026-07-28T10:00:00',
                   '2026-07-15T10:00:00'):
            conn.execute("INSERT INTO events(event_type, message_id, event_ts, "
                         "created_at, dedup_key) VALUES('open', 55, ?, ?, ?)",
                         (ts, ts, 'd-' + ts))
        conn.execute("INSERT INTO events(event_type, message_id, event_ts, "
                     "created_at, dedup_key) VALUES('sent', 55, "
                     "'2026-07-29T10:00:00', '2026-07-29T10:00:00', 'd-sent')")
    rows = st.recent_opens(limit=2)
    assert len(rows) == 2                                   # лимит соблюдён
    assert rows[0]['ts'].startswith('2026-07-28')           # свежие сверху
    assert all(r['message_id'] == 55 for r in rows)          # не-open не попал


def test_empty_when_no_opens():
    assert _store().recent_opens(limit=10) == []
