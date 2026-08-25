# -*- coding: utf-8 -*-
"""Идёт ли отправка сейчас; режим журнала базы."""
import os
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=10)
c.row_factory = sqlite3.Row
print("режим журнала: %s | busy_timeout: %s"
      % (c.execute("PRAGMA journal_mode").fetchone()[0],
         c.execute("PRAGMA busy_timeout").fetchone()[0]))
for ф in ("sender.db-wal", "sender.db-journal"):
    п = r"C:\sender\%s" % ф
    if os.path.exists(п):
        print("  %s: %.1f МБ" % (ф, os.path.getsize(п) / 1048576.0))

print("\n=== ОТПРАВЛЕНО ПО ЧЕТВЕРТЯМ ЧАСА (последние 3 часа) ===")
было = False
for р in c.execute(
        "SELECT substr(sent_at,1,15) т, COUNT(*) n FROM messages "
        " WHERE status='sent' AND sent_at >= datetime('now','-3 hours') "
        " GROUP BY т ORDER BY т"):
    было = True
    print("  %s0  %s %d" % (р["т"], "#" * min(50, р["n"]), р["n"]))
if not было:
    print("  за три часа не ушло НИ ОДНОГО письма")

print("\n=== ПОСЛЕДНИЕ 5 ОТПРАВЛЕННЫХ ===")
for р in c.execute(
        "SELECT id, sent_at, mailbox_id FROM messages WHERE status='sent' "
        " ORDER BY sent_at DESC LIMIT 5"):
    print("  #%-6s %s  %s" % (р["id"], str(р["sent_at"])[:19],
                              str(р["mailbox_id"])[:40]))

print("\n=== ЧТО ЖДЁТ ===")
for р in c.execute(
        "SELECT status, COUNT(*) n FROM messages "
        " WHERE status NOT IN ('sent','skipped','failed') GROUP BY status"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== СВЕЖИЕ ОШИБКИ ОТПРАВКИ ===")
for р in c.execute(
        "SELECT substr(COALESCE(last_error,''),1,70) п, COUNT(*) n FROM messages "
        " WHERE status='failed' AND updated_at >= datetime('now','-1 day') "
        " GROUP BY п ORDER BY n DESC LIMIT 6"):
    print("  %-72s %d" % (р["п"], р["n"]))
