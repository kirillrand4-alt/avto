# -*- coding: utf-8 -*-
"""Только чтение: откуда взялись 5 спам-отказов, закрывших направление meyer."""
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ВСЕ reject_spam ЗА ПОСЛЕДНИЕ СУТКИ ===")
for р in s.execute("SELECT id, created_at, mailbox_id, detail_json FROM events"
                   " WHERE event_type='reject_spam'"
                   " AND created_at >= datetime('now','-24 hour') ORDER BY id"):
    print("  #%-8s %s  %-36s" % (р["id"], str(р["created_at"])[:19],
                                 str(р["mailbox_id"] or "")[:36]))
    d = str(р["detail_json"] or "")
    if d:
        print("     %s" % d[:150])

print("\n=== ПО ЯЩИКАМ ===")
for р in s.execute("SELECT mailbox_id, COUNT(*) n FROM events"
                   " WHERE event_type='reject_spam'"
                   " AND created_at >= datetime('now','-24 hour')"
                   " GROUP BY mailbox_id ORDER BY n DESC"):
    print("  %-40s %d" % (str(р["mailbox_id"] or "(нет)")[:40], р["n"]))

print("\n=== ЗА ПОСЛЕДНИЕ 48 ЧАСОВ ПО ДНЯМ ===")
for р in s.execute("SELECT substr(created_at,1,10) д, COUNT(*) n FROM events"
                   " WHERE event_type='reject_spam' AND created_at >= datetime('now','-3 day')"
                   " GROUP BY д ORDER BY д"):
    print("  %s  %d" % (р["д"], р["n"]))

print("\n=== ИТОГ ===")
n = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='reject_spam'"
              " AND created_at >= datetime('now','-24 hour')").fetchone()["n"]
fs = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='reject_spam'"
               " AND created_at >= datetime('now','-24 hour')"
               " AND mailbox_id LIKE '%food-sort%'").fetchone()["n"]
print("  спам-отказов за сутки по направлению: %d (порог заслона 5)" % n)
print("  из них с food-sort.ru               : %d" % fs)
print("  когда истечёт: заслон считает скользящие сутки, значит по мере")
print("  устаревания событий счётчик опустится ниже 5 и направление откроется")
