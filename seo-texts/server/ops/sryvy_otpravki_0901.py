# -*- coding: utf-8 -*-
"""Только чтение: не срываются ли отправки, реальный темп."""
import sqlite3
from datetime import datetime, timedelta, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row


def iso(мин):
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(minutes=мин)).isoformat()


print("=== ПИСЬМА В sending СЕЙЧАС ===")
for р in s.execute("SELECT id, mailbox_id, claimed_at, attempt_count, last_error"
                   " FROM messages WHERE status='sending' ORDER BY claimed_at"):
    print("  #%-7s %-32s claimed %s попыток %s %s"
          % (р["id"], str(р["mailbox_id"] or "-")[:32], str(р["claimed_at"])[:19],
             р["attempt_count"], str(р["last_error"] or "")[:40]))

print("\n=== FAILED ЗА ЧАС ===")
n = s.execute("SELECT COUNT(*) n FROM messages WHERE status='failed'"
              " AND updated_at >= ?", (iso(60),)).fetchone()["n"]
print("  писем в failed за час: %d" % n)
for р in s.execute("SELECT id, mailbox_id, attempt_count, last_error FROM messages"
                   " WHERE status='failed' AND updated_at >= ? LIMIT 6", (iso(60),)):
    print("  #%-7s %-30s попыток %s | %s"
          % (р["id"], str(р["mailbox_id"] or "-")[:30], р["attempt_count"],
             str(р["last_error"] or "")[:60]))

print("\n=== СОБЫТИЯ ЗА ЧАС ПО ТИПАМ ===")
for р in s.execute("SELECT event_type, COUNT(*) n FROM events WHERE created_at >= ?"
                   " GROUP BY event_type ORDER BY n DESC", (iso(60),)):
    print("  %-16s %d" % (р["event_type"], р["n"]))

print("\n=== ИТОГ: РЕАЛЬНЫЙ ТЕМП ===")
for м in (10, 20, 30, 60):
    n = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= ?", (iso(м),)).fetchone()["n"]
    print("  за %2d мин: %3d писем (%.2f/мин)" % (м, n, n / float(м)))
оч = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
n30 = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                " AND created_at >= ?", (iso(30),)).fetchone()["n"]
мск = datetime.now()
до = (14 * 60) - (мск.hour * 60 + мск.minute)
темп = n30 / 30.0
print("  в очереди %d, мск %s, до окна %d мин" % (оч, мск.strftime("%H:%M"), до))
print("  при темпе %.2f/мин за оставшееся время: %d писем" % (темп, int(темп * до)))
