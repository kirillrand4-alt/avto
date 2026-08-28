# -*- coding: utf-8 -*-
import sqlite3
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
print("=== ВСЕ строки обогащения для ИНН 5948073993 ===")
for r in e.execute("SELECT email, role, person, probe_verdict FROM emails "
                   " WHERE inn='5948073993' ORDER BY role, email"):
    print("   %-30s %-22s %s" % (r["email"], str(r["role"])[:22],
                                 str(r["person"] or "")[:22]))
print("")
print("=== один адрес под сколькими ИНН ===")
for r in e.execute("SELECT email, COUNT(DISTINCT inn) n, COUNT(DISTINCT role) rr "
                   "  FROM emails WHERE email LIKE '%@incab.ru' "
                   " GROUP BY email HAVING n > 1 ORDER BY n DESC"):
    print("   %-30s ИНН: %d, разных ролей: %d" % (r["email"], r["n"], r["rr"]))
print("")
print("=== масштаб по всей базе ===")
r = e.execute("SELECT COUNT(*) FROM (SELECT email FROM emails "
              " GROUP BY email HAVING COUNT(DISTINCT inn) > 1)").fetchone()[0]
r2 = e.execute("SELECT COUNT(*) FROM (SELECT email FROM emails "
               " GROUP BY email HAVING COUNT(DISTINCT role) > 1)").fetchone()[0]
всего = e.execute("SELECT COUNT(DISTINCT email) FROM emails").fetchone()[0]
print("   адресов всего: %d" % всего)
print("   под разными ИНН: %d (%.1f%%)" % (r, 100.0 * r / всего))
print("   с разными ролями: %d (%.1f%%)" % (r2, 100.0 * r2 / всего))
e.close()
