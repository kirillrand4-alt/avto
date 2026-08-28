# -*- coding: utf-8 -*-
"""Зависшие в sending: ушли они на самом деле или нет."""
import sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT m.id, m.scheduled_at, m.claimed_at, m.sent_at, m.rfc_message_id, "
    "       m.attempt_count, m.last_error, m.mailbox_id, rc.email "
    "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
    " WHERE m.status='sending' ORDER BY m.scheduled_at").fetchall()
print("в статусе sending: %d" % len(строки))
сч = Counter()
для_возврата = []
for r in строки:
    есть_rfc = bool(r["rfc_message_id"])
    есть_sent = bool(r["sent_at"])
    ev = c.execute("SELECT COUNT(*) FROM events WHERE message_id=? "
                   "   AND event_type='sent'", (r["id"],)).fetchone()[0]
    лог = c.execute("SELECT COUNT(*) FROM send_log WHERE message_id=? "
                    "   AND outcome='sent'", (r["id"],)).fetchone()[0]
    if есть_sent or ev or лог or есть_rfc:
        сч["ПОХОЖЕ УШЛО (есть след)"] += 1
        print("   msg %-6s %-26s sent_at=%s rfc=%s событий=%d лог=%d"
              % (r["id"], str(r["email"])[:26], str(r["sent_at"] or "—")[:16],
                 "да" if есть_rfc else "нет", ev, лог))
    else:
        сч["следов отправки нет"] += 1
        для_возврата.append(r["id"])
print("")
for к, n in сч.most_common():
    print("   %-30s %4d" % (к, n))
print("")
print("=== попытки и ошибки у зависших ===")
for к, n in Counter("попыток %s | %s" % (r["attempt_count"],
                                         str(r["last_error"] or "—")[:44])
                    for r in строки).most_common(6):
    print("   %-64s %3d" % (к, n))
print("")
print("к возврату в расписание: %d" % len(для_возврата))
print("   %s" % str(для_возврата)[:200])
c.close()
