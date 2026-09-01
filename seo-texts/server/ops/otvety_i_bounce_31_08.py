# -*- coding: utf-8 -*-
"""Только чтение: что панель считает ответом и откуда сегодняшние отбивки."""
import inspect
import re
import sqlite3

print("=== ЧТО analytics СЧИТАЕТ ОТВЕТОМ ===")
import sys
sys.path.insert(0, r"C:\sender")
import sender.analytics as A  # noqa: E402
src = inspect.getsource(A)
for m in re.finditer(r"[^\n]*repl[^\n]*", src):
    x = m.group(0).strip()
    if "def " in x or "reply" in x:
        print("  " + x[:108])

print("\n=== СЕГОДНЯШНИЕ ОТБИВКИ ПО ЯЩИКАМ ===")
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
for р in s.execute("SELECT mailbox_id, event_type, COUNT(*) n FROM events"
                   " WHERE created_at >= date('now')"
                   " AND event_type IN ('bounce','reject_spam','suppress')"
                   " GROUP BY mailbox_id, event_type ORDER BY n DESC"):
    print("  %-38s %-14s %d" % (str(р["mailbox_id"] or "(нет)")[:38],
                                р["event_type"], р["n"]))

print("\n=== СЕГОДНЯ: ОТПРАВЛЕНО И ОТБИТО ПО ЯЩИКАМ ===")
от = {}
for р in s.execute("SELECT mailbox_id, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= date('now')"
                   " GROUP BY mailbox_id"):
    от[str(р["mailbox_id"])] = р["n"]
бо = {}
for р in s.execute("SELECT mailbox_id, COUNT(*) n FROM events"
                   " WHERE event_type IN ('bounce','reject_spam')"
                   " AND created_at >= date('now') GROUP BY mailbox_id"):
    бо[str(р["mailbox_id"])] = р["n"]
print("  %-38s %8s %8s %8s" % ("ящик", "ушло", "отбито", "доля"))
for m in sorted(set(от) | set(бо)):
    о, b = от.get(m, 0), бо.get(m, 0)
    print("  %-38s %8d %8d %7.0f%%" % (m[:38], о, b, 100.0 * b / max(1, о)))

print("\n=== ИТОГ: СОБЫТИЕ ОТВЕТА СЕГОДНЯ ===")
for р in s.execute("SELECT id, event_type, created_at, mailbox_id, detail_json FROM events"
                   " WHERE event_type LIKE '%repl%' AND created_at >= date('now')"):
    print("  #%s %s %s %s" % (р["id"], р["event_type"], str(р["created_at"])[:19],
                              р["mailbox_id"]))
    print("     detail: %s" % str(р["detail_json"] or "")[:220])
