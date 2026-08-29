# -*- coding: utf-8 -*-
"""Насколько полна база обзвона: сколько компаний со сделкой в ней есть.

Компании со сделкой владелец загружал в стоп-лист причиной deal_in_progress —
это единственный список «наших реальных клиентов» в машиночитаемом виде.
Пересекаем его с базой обзвона (161k) и с обогащением.
"""
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
c.row_factory = sqlite3.Row
причины = Counter()
сделки = set()
прочие_инн = set()
for r in c.execute("SELECT scope, value, reason FROM suppression"):
    if str(r["reason"]) == "deal_in_progress":
        причины[r["scope"]] += 1
        if r["scope"] == "inn":
            сделки.add(цифры(r["value"]))
    elif r["scope"] == "inn":
        прочие_инн.add(цифры(r["value"]))
сделки.discard("")
print("записей deal_in_progress по разрезам: %s" % dict(причины))
print("уникальных ИНН со сделкой: %d" % len(сделки))
# получатели и компании, которых мы вообще знаем
получатели = {цифры(r[0]) for r in c.execute(
    "SELECT inn FROM recipients WHERE inn IS NOT NULL")}
получатели.discard("")
c.close()

обзвон = set()
имена = {}
try:
    o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
    o.row_factory = sqlite3.Row
    кол = {r["name"] for r in o.execute("PRAGMA table_info(obzvon)")}
    поле_имя = "name_short" if "name_short" in кол else None
    for r in o.execute("SELECT inn%s FROM obzvon"
                       % (", " + поле_имя if поле_имя else "")):
        и = цифры(r["inn"])
        if и:
            обзвон.add(и)
            if поле_имя:
                имена[и] = r[поле_имя]
    o.close()
except Exception as ex:
    print("обзвон не прочитан: %s" % ex)

обог = set()
имена_обог = {}
try:
    e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
    e.row_factory = sqlite3.Row
    for r in e.execute("SELECT inn, COALESCE(short_name, name) AS nm FROM companies"):
        и = цифры(r["inn"])
        if и:
            обог.add(и)
            имена_обог[и] = r["nm"]
    e.close()
except Exception as ex:
    print("обогащение не прочитано: %s" % ex)

print("\nкомпаний в базе обзвона: %d" % len(обзвон))
print("компаний в обогащении:   %d" % len(обог))
print("получателей с ИНН в панели: %d" % len(получатели))

в_обзвоне = сделки & обзвон
в_обог = сделки & обог
в_панели = сделки & получатели
нигде = сделки - обзвон - обог - получатели
print("\n=== СДЕЛКИ ПРОТИВ НАШИХ БАЗ ===")
print("   всего компаний со сделкой:      %d" % len(сделки))
print("   есть в базе обзвона:            %d  (%.1f%%)"
      % (len(в_обзвоне), 100.0 * len(в_обзвоне) / len(сделки) if сделки else 0))
print("   есть в обогащении:              %d  (%.1f%%)"
      % (len(в_обог), 100.0 * len(в_обог) / len(сделки) if сделки else 0))
print("   заведены получателями в панели: %d  (%.1f%%)"
      % (len(в_панели), 100.0 * len(в_панели) / len(сделки) if сделки else 0))
print("   НЕТ НИГДЕ:                      %d  (%.1f%%)"
      % (len(нигде), 100.0 * len(нигде) / len(сделки) if сделки else 0))
print("\n   есть в обогащении, но НЕТ в обзвоне: %d" % len(в_обог - обзвон))
print("   есть в обзвоне, но НЕ заведены получателями: %d"
      % len(в_обзвоне - получатели))
print("\n=== кого нет нигде (первые 25 ИНН) ===")
for и in sorted(нигде)[:25]:
    print("   %s" % и)
print("\n=== примеры тех, кто есть в обзвоне (с названиями) ===")
показано = 0
for и in sorted(в_обзвоне):
    имя = имена.get(и) or имена_обог.get(и) or ""
    if имя:
        print("   %-14s %s" % (и, str(имя)[:52]))
        показано += 1
    if показано >= 10:
        break
