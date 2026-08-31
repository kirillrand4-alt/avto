# -*- coding: utf-8 -*-
"""Разведка перед подсчётом: значения division, source почты, выручка."""
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
print("=== companies.division ===")
for r in c.execute("SELECT COALESCE(NULLIF(TRIM(division),''),'(пусто)') d, "
                   "COUNT(*) n FROM companies GROUP BY d ORDER BY n DESC LIMIT 15"):
    print("   %-22s %7d" % (r[0], r[1]))

print("\n=== emails.source ===")
for r in c.execute("SELECT COALESCE(NULLIF(TRIM(source),''),'(пусто)') s, "
                   "COUNT(*) n FROM emails GROUP BY s ORDER BY n DESC LIMIT 20"):
    print("   %-26s %7d" % (r[0], r[1]))

print("\n=== emails.addr_class ===")
for r in c.execute("SELECT COALESCE(NULLIF(TRIM(addr_class),''),'(пусто)') s, "
                   "COUNT(*) n FROM emails GROUP BY s ORDER BY n DESC LIMIT 12"):
    print("   %-26s %7d" % (r[0], r[1]))

print("\n=== выручка в companies (тип INTEGER) ===")
for r in c.execute("""SELECT CASE
        WHEN revenue_rub IS NULL OR revenue_rub=0 THEN 'нет данных'
        WHEN revenue_rub < 30000000 THEN 'меньше 30 млн'
        WHEN revenue_rub < 100000000 THEN '30-100 млн'
        WHEN revenue_rub < 500000000 THEN '100-500 млн'
        ELSE 'больше 500 млн' END k, COUNT(*) n
      FROM companies GROUP BY k ORDER BY n DESC"""):
    print("   %-18s %7d" % (r[0], r[1]))

print("\n=== выручка у мейеровских ===")
for r in c.execute("""SELECT CASE
        WHEN revenue_rub IS NULL OR revenue_rub=0 THEN 'нет данных'
        WHEN revenue_rub < 30000000 THEN 'меньше 30 млн'
        ELSE '30 млн и больше' END k, COUNT(*) n
      FROM companies WHERE division LIKE '%meyer%' GROUP BY k ORDER BY n DESC"""):
    print("   %-18s %7d" % (r[0], r[1]))

print("\n=== есть ли сайт у мейеровских ===")
r = c.execute("""SELECT COUNT(*),
       SUM(CASE WHEN COALESCE(NULLIF(TRIM(site),''),'')<>'' THEN 1 ELSE 0 END),
       SUM(CASE WHEN COALESCE(NULLIF(TRIM(best_email),''),'')<>'' THEN 1 ELSE 0 END)
     FROM companies WHERE division LIKE '%meyer%'""").fetchone()
print("   мейеровских компаний %d; с сайтом %d; с best_email %d" % r)
c.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
print("\n=== recipients.segment ===")
for r in s.execute("SELECT COALESCE(NULLIF(TRIM(segment),''),'(пусто)') g, "
                   "COUNT(*) n FROM recipients GROUP BY g ORDER BY n DESC LIMIT 12"):
    print("   %-26s %7d" % (r[0], r[1]))
print("\n=== кампании ===")
for r in s.execute("SELECT id, name, status FROM campaigns ORDER BY id"):
    print("   %2s  %-38s %s" % r)
s.close()
