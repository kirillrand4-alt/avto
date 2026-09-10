# -*- coding: utf-8 -*-
"""Кем были отбитые адреса ДО отбивки: вердикт из обогащения, где он уцелел.

addr_probe отбивка перезаписывает (source=hard-bounce), и прежний вердикт
там теряется. В enrich.db вердикт лежит отдельно и мог уцелеть.
"""
import sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    мид = next((c for c in ("message_id", "msg_id") if c in кол), None)
    письма = {int(r["id"]): str(r["email"] or "").lower()
              for r in store._conn.execute(
                  "SELECT m.id, r.email FROM messages m "
                  "  LEFT JOIN recipients r ON m.recipient_id = r.id "
                  " WHERE m.sent_at >= datetime('now','-5 days')")}
    отбитые = set()
    for r in store._conn.execute(
            "SELECT %s m FROM events WHERE %s='bounce' AND %s >= "
            "datetime('now','-5 days')" % (мид, тп, вр)):
        а = письма.get(int(r["m"] or 0), "")
        if а:
            отбитые.add(а)
    # для сравнения: адреса, которые ушли и НЕ отбились
    ушли = {а for а in письма.values() if а}
    не_отбились = ушли - отбитые

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
обог = {}
try:
    for e, v in c.execute("SELECT email, probe_verdict FROM emails "
                          " WHERE probe_verdict IS NOT NULL AND probe_verdict<>''"):
        обог[str(e or "").lower()] = str(v or "")
except Exception as ex:                                         # noqa: BLE001
    print("enrich.emails не прочитались: %s" % str(ex)[:90])
c.close()

бы = Counter()
для_чистых = Counter()
for а in отбитые:
    бы[обог.get(а) or "в обогащении нет вердикта"] += 1
for а in не_отбились:
    для_чистых[обог.get(а) or "в обогащении нет вердикта"] += 1

print("--- ОТБИТЫЕ адреса: чем они были в обогащении ---")
for к, в in бы.most_common():
    print("   %-32s %5d" % (к, в))
print("")
print("--- НЕ отбившиеся: чем были они ---")
for к, в in для_чистых.most_common():
    print("   %-32s %5d" % (к, в))
print("")
print("=" * 74)
print("=== ЧЕМ БЫЛИ ОТБИТЫЕ ДО ОТБИВКИ (5 дней) ===")
print("отбитых адресов: %d; ушедших без отбивки: %d"
      % (len(отбитые), len(не_отбились)))
для = обог and (бы.get("принимает всё", 0), для_чистых.get("принимает всё", 0))
if для:
    о, ч = для
    print("доля «принимает всё» среди отбитых:     %.1f%%"
          % (100.0 * о / max(1, len(отбитые))))
    print("доля «принимает всё» среди не отбитых:  %.1f%%"
          % (100.0 * ч / max(1, len(не_отбились))))
