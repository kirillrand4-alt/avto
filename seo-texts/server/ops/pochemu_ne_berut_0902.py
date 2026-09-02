# -*- coding: utf-8 -*-
"""Только чтение: гоняем ТОТ ЖЕ запрос, что и цикл, и смотрим, есть ли наши."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
now_iso = dt.datetime.now().isoformat()

sql = """SELECT m.id AS mid, m.campaign_id, m.scheduled_at FROM messages m
         WHERE m.status='scheduled' AND m.scheduled_at <= ?
           AND (SELECT cr.status FROM confirm_reviews cr
                 WHERE cr.message_id=m.id
                 ORDER BY cr.id DESC LIMIT 1)
               IN ('approved','edited')
         ORDER BY m.scheduled_at, m.id LIMIT ?"""

for лимит in (10, 60, 400):
    ряды = list(c.execute(sql, (now_iso, лимит)))
    из12 = sum(1 for р in ряды if р["campaign_id"] == 12)
    print("limit=%-4d вернулось %3d, из них кампании 12: %d" % (лимит, len(ряды), из12))

ряды = list(c.execute(sql, (now_iso, 400)))
по = {}
for р in ряды:
    по[р["campaign_id"]] = по.get(р["campaign_id"], 0) + 1
print("  по кампаниям: %s" % по)

print("\n=== ПОЧЕМУ НАШИ НЕ ПОПАДАЮТ ===")
н = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
              " AND status='scheduled' AND scheduled_at<=?", (now_iso,)).fetchone()[0]
print("  наших scheduled и созревших: %d" % н)
о = c.execute("SELECT COUNT(*) FROM messages m WHERE m.campaign_id=12"
              " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
              " ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')").fetchone()[0]
print("  из них с последним ревью approved/edited: %d" % о)
print("\n  статусы последних ревью по нашим письмам:")
for р in c.execute("SELECT (SELECT cr.status FROM confirm_reviews cr"
                   " WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) ст,"
                   " COUNT(*) k FROM messages m WHERE m.campaign_id=12 GROUP BY ст"):
    print("    %-14s %d" % (str(р["ст"]), р["k"]))
