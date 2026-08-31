# -*- coding: utf-8 -*-
"""Проверка честности счёта: не сработали ли фильтры вхолостую."""
import sqlite3
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
print("=== заполненность полей у мейеровских ===")
r = e.execute("""SELECT COUNT(*),
   SUM(CASE WHEN COALESCE(is_competitor,0)<>0 THEN 1 ELSE 0 END),
   SUM(CASE WHEN COALESCE(NULLIF(TRIM(status_egrul),''),'')<>'' THEN 1 ELSE 0 END),
   SUM(CASE WHEN LOWER(COALESCE(status_egrul,'')) LIKE '%ликвид%'
            OR LOWER(COALESCE(status_egrul,'')) LIKE '%банкрот%' THEN 1 ELSE 0 END)
   FROM companies WHERE division LIKE '%meyer%'""").fetchone()
print("   всего %d; помечены конкурентами %d; статус ЕГРЮЛ заполнен %d; "
      "из них ликвид/банкрот %d" % r)

print("\n=== вклад источников почты (мейер, выручка подходит) ===")
for r in e.execute("""SELECT em.source, COUNT(DISTINCT em.inn) n
   FROM emails em JOIN companies c ON c.inn=em.inn
   WHERE c.division LIKE '%meyer%'
     AND (c.revenue_rub IS NULL OR c.revenue_rub=0 OR c.revenue_rub>=30000000)
     AND em.source IN ('own-site','обзвон-сайт','сайт:справочник')
   GROUP BY em.source ORDER BY n DESC"""):
    print("   %-22s компаний %6d" % (r[0], r[1]))
e.close()
