# -*- coding: utf-8 -*-
"""Только чтение: знаем ли мы, что производят наши 175 адресатов."""
import sqlite3

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

инн = [р["inn"] for р in s.execute(
    "SELECT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12") if р["inn"]]
всего = s.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0]
print("писем %d, из них с ИНН %d" % (всего, len(инн)))

есть = 0
примеры = []
if инн:
    впис = ",".join("?" * len(инн))
    for р in e.execute("SELECT inn, name, activity, okved FROM companies"
                       " WHERE inn IN (%s)" % впис, инн):
        а = (р["activity"] or "").strip()
        if len(а) >= 15:
            есть += 1
            if len(примеры) < 8:
                примеры.append((р["name"][:34], а[:70]))
print("  с внятным описанием деятельности: %d" % есть)
for н, а in примеры:
    print("    %-34s %s" % (н, а))

print("\n=== ОКВЭД-группы адресатов ===")
if инн:
    впис = ",".join("?" * len(инн))
    гр = {}
    for р in e.execute("SELECT okved FROM companies WHERE inn IN (%s)" % впис, инн):
        к = (р["okved"] or "")[:5]
        гр[к] = гр.get(к, 0) + 1
    for к, n in sorted(гр.items(), key=lambda x: -x[1])[:10]:
        print("  %-8s %3d" % (к or "нет", n))
