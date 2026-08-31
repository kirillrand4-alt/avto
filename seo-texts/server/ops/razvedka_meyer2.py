# -*- coding: utf-8 -*-
"""Голова списков, которую срезал хвост вывода."""
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
print("=== companies.division ===")
for r in c.execute("SELECT COALESCE(NULLIF(TRIM(division),''),'(пусто)') d, "
                   "COUNT(*) n FROM companies GROUP BY d ORDER BY n DESC LIMIT 12"):
    print("   %-24s %7d" % (r[0], r[1]))
print("\n=== emails.source: первые 14 ===")
for r in c.execute("SELECT COALESCE(NULLIF(TRIM(source),''),'(пусто)') s, "
                   "COUNT(*) n FROM emails GROUP BY s ORDER BY n DESC LIMIT 14"):
    print("   %-30s %7d" % (r[0], r[1]))
print("\n=== source_url заполнен? ===")
r = c.execute("SELECT COUNT(*), SUM(CASE WHEN COALESCE(NULLIF(TRIM(source_url),''),'')"
              "<>'' THEN 1 ELSE 0 END) FROM emails").fetchone()
print("   всего адресов %d, с source_url %d" % r)
c.close()
