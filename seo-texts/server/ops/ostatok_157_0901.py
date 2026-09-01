# -*- coding: utf-8 -*-
"""Только чтение: почему остаток очереди не уходит."""
import sqlite3
from collections import Counter
from datetime import datetime, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

print("=== ОСТАТОК: ВРЕМЯ НАЗНАЧЕНИЯ ===")
for р in s.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' GROUP BY ч ORDER BY ч"):
    d = р["ч"]
    try:
        dt = datetime.strptime(d, "%Y-%m-%dT%H")
        мск = " = %02d:00 мск %s" % ((dt.hour + 3) % 24, dt.strftime("%d.%m"))
    except Exception:
        мск = ""
    print("  %s  %4d%s" % (d, р["n"], мск))

print("\n=== СТАТУС КАРТОЧКИ У ОСТАТКА ===")
for р in s.execute("SELECT COALESCE((SELECT cr.status FROM confirm_reviews cr"
                   " WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1),'(нет)') st,"
                   " COUNT(*) n FROM messages m WHERE m.status='scheduled'"
                   " GROUP BY st ORDER BY n DESC"):
    print("  %-16s %4d" % (р["st"], р["n"]))

print("\n=== ПОЯСА ОСТАТКА ===")
for р in s.execute("SELECT COALESCE(NULLIF(r.tz,''),'(пусто->мск)') tz, COUNT(*) n"
                   " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.status='scheduled' GROUP BY tz ORDER BY n DESC"):
    print("  %-24s %4d" % (р["tz"], р["n"]))

print("\n=== ИТОГ ===")
созр = s.execute("SELECT COUNT(*) n FROM messages m WHERE m.status='scheduled'"
                 " AND m.scheduled_at <= ?"
                 " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
                 "      ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')",
                 (now_iso,)).fetchone()["n"]
вс = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
print("  в очереди %d, из них созрели И одобрены: %d" % (вс, созр))
print("  сейчас мск %s" % datetime.now().strftime("%H:%M"))
print("  если созревших и одобренных 0 — остаток назначен на завтра, это норма")
