# -*- coding: utf-8 -*-
"""Только чтение. Что нужно знать перед заводом группы vebinar-2609:
схема recipients, кампании, стоп-лист по ИНН, справочник компаний."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def таблицы(конн):
    return [r[0] for r in конн.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


print("=== ТАБЛИЦЫ sender.db ===")
print("  " + ", ".join(таблицы(c)))

print("\n=== recipients: колонки ===")
кол = [r["name"] for r in c.execute("PRAGMA table_info(recipients)")]
print("  " + ", ".join(кол))
print("  всего: %d" % c.execute("SELECT COUNT(*) FROM recipients").fetchone()[0])

р = c.execute("SELECT * FROM recipients WHERE extra_json LIKE '%gruppy%'"
              " ORDER BY id DESC LIMIT 1").fetchone()
if р:
    print("\n=== ПРИМЕР recipients (последний с группой) ===")
    for k in кол:
        v = р[k]
        if k == "extra_json" and v:
            d = json.loads(v)
            print("  extra_json ключи: %s" % ", ".join(sorted(d.keys())))
            for kk in sorted(d.keys()):
                print("      %-24s %s" % (kk, str(d[kk])[:70]))
        else:
            print("  %-16s %s" % (k, str(v)[:70]))

print("\n=== КАМПАНИИ ===")
if "campaigns" in таблицы(c):
    кк = [r["name"] for r in c.execute("PRAGMA table_info(campaigns)")]
    print("  колонки: %s" % ", ".join(кк))
    for р2 in c.execute("SELECT * FROM campaigns ORDER BY id"):
        print("  " + " | ".join("%s=%s" % (k, str(р2[k])[:46]) for k in кк))
else:
    print("  таблицы campaigns нет")

print("\n=== ГРУППЫ, КОТОРЫЕ УЖЕ ЕСТЬ ===")
счёт = {}
for р3 in c.execute("SELECT extra_json FROM recipients"
                    " WHERE extra_json LIKE '%gruppy%'"):
    try:
        for g in (json.loads(р3["extra_json"]).get("gruppy") or []):
            счёт[g] = счёт.get(g, 0) + 1
    except Exception:
        pass
for g, n in sorted(счёт.items(), key=lambda x: -x[1])[:15]:
    print("  %-34s %6d" % (g, n))

print("\n=== СТОП-ЛИСТ ПО ИНН ===")
print("  записей scope=inn: %d"
      % c.execute("SELECT COUNT(*) FROM suppression WHERE scope='inn'").fetchone()[0])

print("\n=== СПРАВОЧНИК КОМПАНИЙ (enrich.db) ===")
try:
    e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
    e.row_factory = sqlite3.Row
    print("  таблицы: %s" % ", ".join(таблицы(e)))
    ек = [r["name"] for r in e.execute("PRAGMA table_info(companies)")]
    print("  companies: %s" % ", ".join(ек))
    print("  строк: %d" % e.execute("SELECT COUNT(*) FROM companies").fetchone()[0])
    об = e.execute("SELECT * FROM companies LIMIT 1").fetchone()
    if об:
        print("  пример: " + " | ".join("%s=%s" % (k, str(об[k])[:34]) for k in ек[:12]))
except Exception as ex:
    print("  ошибка enrich.db: %s" % str(ex)[:150])

print("\n=== ИТОГ РАЗВЕДКИ ===")
print("  выше: схема recipients, список кампаний, имена групп, размер стоп-листа")
