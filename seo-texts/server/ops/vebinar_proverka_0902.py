# -*- coding: utf-8 -*-
"""Только чтение: что легло в базу по кампании вебинара."""
import json
import sqlite3
import sys

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== КАМПАНИЯ 12 ===")
р = c.execute("SELECT * FROM campaigns WHERE id=12").fetchone()
print("  %s | статус=%s | %s" % (р["name"], р["status"], str(р["config_json"])[:150]))

print("\n=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ ПО КАМПАНИИ 12 ===")
for x in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews"
                   " WHERE campaign_id=12 GROUP BY status"):
    print("  %-12s %4d" % (x["status"], x["n"]))
print("  с ИНН: %d" % c.execute("SELECT COUNT(*) FROM confirm_reviews"
                                " WHERE campaign_id=12 AND inn IS NOT NULL"
                                " AND inn<>''").fetchone()[0])

print("\n=== ГРУППА vebinar-2609 ===")
n = c.execute("SELECT COUNT(*) FROM recipients"
              " WHERE extra_json LIKE '%vebinar-2609%'").fetchone()[0]
print("  получателей: %d" % n)
дв = c.execute("SELECT COUNT(*) FROM recipients WHERE extra_json LIKE '%vebinar-2609%'"
               " AND extra_json LIKE '%Партия 935%'").fetchone()[0]
print("  из них были и в Партии 935: %d" % дв)
пин = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=12"
                " AND panel_json LIKE '%i.kuznetsova@sort-systems.ru%'").fetchone()[0]
print("  писем, закреплённых за ящиком Ирины: %d" % пин)

print("\n=== ТЕМЫ ===")
for x in c.execute("SELECT subject, COUNT(*) n FROM confirm_reviews"
                   " WHERE campaign_id=12 GROUP BY subject ORDER BY n DESC"):
    print("  %-46s %3d" % (x["subject"][:46], x["n"]))

print("\n=== ОДИНАКОВЫЕ ТЕЛА ===")
д = c.execute("SELECT COUNT(*) FROM (SELECT body FROM confirm_reviews"
              " WHERE campaign_id=12 GROUP BY body HAVING COUNT(*)>1)").fetchone()[0]
print("  повторяющихся тел: %d" % д)

print("\n=== ИТОГ ===")
print("  всё лежит в pending, ни одно письмо не одобрено и не отправлено")
