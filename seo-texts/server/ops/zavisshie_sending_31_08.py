# -*- coding: utf-8 -*-
"""Только чтение: ушли ли письма, застрявшие в статусе sending."""
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
ряды = list(s.execute("SELECT id, campaign_id, recipient_id, mailbox_id, claimed_at,"
                      " sent_at, rfc_message_id, attempt_count, last_error"
                      " FROM messages WHERE status='sending' ORDER BY claimed_at"))
print("=== ЗАВИСШИЕ В sending: %d ===" % len(ряды))
print("  %-8s %-6s %-20s %-8s %-8s %-8s %s"
      % ("id", "камп", "claimed", "sent_at", "rfc_id", "попыток", "ошибка"))
for р in ряды:
    n_ev = s.execute("SELECT COUNT(*) n FROM events WHERE message_id=?"
                     " AND event_type='sent'", (р["id"],)).fetchone()["n"]
    n_sl = s.execute("SELECT COUNT(*) n FROM send_log WHERE message_id=?",
                     (р["id"],)).fetchone()["n"]
    print("  %-8s %-6s %-20s %-8s %-8s %-8s %s"
          % (р["id"], р["campaign_id"], str(р["claimed_at"])[:19],
             "ЕСТЬ" if р["sent_at"] else "нет",
             "ЕСТЬ" if р["rfc_message_id"] else "нет",
             р["attempt_count"], str(р["last_error"] or "")[:34]))
    print("       события sent: %d | записей send_log: %d" % (n_ev, n_sl))

print("\n=== ИТОГ ===")
ушли = 0
for р in ряды:
    if р["sent_at"] or р["rfc_message_id"]:
        ушли += 1
print("  всего застряло: %d" % len(ряды))
print("  из них с признаком реальной отправки (sent_at или rfc_message_id): %d" % ушли)
print("  без признака отправки (можно вернуть в очередь): %d" % (len(ряды) - ушли))
