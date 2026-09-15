# -*- coding: utf-8 -*-
"""Сколько карточек и писем у нас на один домен topfood.ru."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    print("--- получатели домена topfood.ru ---")
    for р in c.execute(
            "SELECT id, email, company_name, inn FROM recipients "
            " WHERE email LIKE ? ORDER BY id", ("%@topfood.ru",)):
        писем = c.execute(
            "SELECT COUNT(*) FROM messages WHERE recipient_id=?",
            (р["id"],)).fetchone()[0]
        print("   #%-7s %-26s ИНН %-13s %-26s писем %d"
              % (р["id"], р["email"], р["inn"],
                 str(р["company_name"])[:26], писем))

    print("")
    print("--- все письма на домен, по времени ---")
    for р in c.execute(
            "SELECT m.id, m.status, m.sent_at, m.scheduled_at, m.mailbox_id, "
            "       m.campaign_id, r.email, r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id=r.id "
            " WHERE r.email LIKE ? ORDER BY COALESCE(m.sent_at, m.scheduled_at)",
            ("%@topfood.ru",)):
        к = c.execute("SELECT name FROM campaigns WHERE id=?",
                      (р["campaign_id"],)).fetchone()
        print("   %-16s %-14s -> %-26s ИНН %s"
              % (str(р["sent_at"] or р["scheduled_at"] or "-")[:16],
                 р["status"], р["email"], р["inn"]))
        print("       кампания %-26s ящик %s"
              % (str(к["name"] if к else "")[:26], str(р["mailbox_id"] or "-")))

    print("")
    print("--- ответы с этого домена ---")
    for р in c.execute(
            "SELECT e.id, e.event_type, e.event_ts, e.mailbox_id, r.email "
            "  FROM events e JOIN recipients r ON e.recipient_id=r.id "
            " WHERE r.email LIKE ? AND e.event_type LIKE 'reply%' ORDER BY e.id",
            ("%@topfood.ru",)):
        print("   #%-7s %s %-12s писали на %s"
              % (р["id"], str(р["event_ts"])[:19], р["event_type"], р["email"]))
print("")
print("=" * 74)
print("=== ОДИН ДОМЕН topfood.ru ===")
