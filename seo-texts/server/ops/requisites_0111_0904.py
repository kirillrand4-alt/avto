# -*- coding: utf-8 -*-
"""Только чтение: что за компании 01.11 в requisites и годятся ли они."""
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
кол = [r["name"] for r in e.execute("PRAGMA table_info(requisites)")]
print("=== requisites: колонки ===")
print("  %s" % ", ".join(кол))
print("  строк всего: %d" % e.execute("SELECT COUNT(*) FROM requisites").fetchone()[0])
print("  разных ИНН: %d"
      % e.execute("SELECT COUNT(DISTINCT inn) FROM requisites").fetchone()[0])

print("\n=== 01.11 В requisites ===")
n = e.execute("SELECT COUNT(*) FROM requisites WHERE okved_main LIKE '01.11%'"
              ).fetchone()[0]
ун = e.execute("SELECT COUNT(DISTINCT inn) FROM requisites"
               " WHERE okved_main LIKE '01.11%'").fetchone()[0]
print("  строк: %d, разных ИНН: %d" % (n, ун))
print("\n  пример записи:")
р = e.execute("SELECT * FROM requisites WHERE okved_main LIKE '01.11%' LIMIT 1"
              ).fetchone()
for k in кол:
    v = str(р[k])
    if v not in ("None", ""):
        print("    %-22s %s" % (k, v[:70]))

print("\n=== ПЕРЕСЕЧЕНИЕ С companies ===")
инн = [р["inn"] for р in e.execute("SELECT DISTINCT inn FROM requisites"
                                   " WHERE okved_main LIKE '01.11%'")]
есть = 0
for i in range(0, len(инн), 900):
    к = инн[i:i + 900]
    q = ",".join("?" * len(к))
    есть += e.execute("SELECT COUNT(*) FROM companies WHERE inn IN (%s)" % q,
                      к).fetchone()[0]
print("  из %d уже есть в companies: %d, новых: %d" % (len(инн), есть, len(инн) - есть))

print("\n=== ЕСТЬ ЛИ У НИХ ВЫРУЧКА И ПОЧТА ===")
поля = [k for k in кол if any(s in k.lower() for s in
                              ("revenue", "vyruch", "email", "pochta", "site"))]
print("  подходящие поля: %s" % поля)
for п in поля:
    k = e.execute("SELECT COUNT(*) FROM requisites WHERE okved_main LIKE '01.11%%'"
                  " AND %s IS NOT NULL AND %s<>''" % (п, п)).fetchone()[0]
    print("    %-20s заполнено у %d" % (п, k))
почт = e.execute("SELECT COUNT(DISTINCT e.inn) FROM emails e JOIN requisites r"
                 " ON r.inn=e.inn WHERE r.okved_main LIKE '01.11%'").fetchone()[0]
print("  из них есть хоть одна почта в emails: %d" % почт)
