# -*- coding: utf-8 -*-
"""Только чтение: колонки companies/email_sources и как выглядят домены."""
import sqlite3

c = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for tn in ("companies", "email_sources", "emails"):
    try:
        кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % tn)]
        n = c.execute("SELECT COUNT(*) FROM %s" % tn).fetchone()[0]
        print("-- %s (%d строк): %s" % (tn, n, ", ".join(кол)))
        р = c.execute("SELECT * FROM %s LIMIT 2" % tn).fetchall()
        for x in р:
            print("     ", {k: (str(x[k])[:48]) for k in кол[:9]})
    except Exception as e:
        print("-- %s: %s" % (tn, str(e)[:70]))

print("\n=== site_facts.site: как выглядит ===")
for р in c.execute("SELECT site FROM site_facts WHERE site IS NOT NULL"
                   " AND site<>'' LIMIT 8"):
    print("   ", р["site"])
print("  со схемой http:",
      c.execute("SELECT COUNT(*) FROM site_facts WHERE site LIKE 'http%'").fetchone()[0])
print("  с www.       :",
      c.execute("SELECT COUNT(*) FROM site_facts WHERE site LIKE 'www.%'").fetchone()[0])
print("  всего непустых:",
      c.execute("SELECT COUNT(*) FROM site_facts WHERE site IS NOT NULL AND site<>''"
                ).fetchone()[0])

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("\n=== recipients.domain: как выглядит ===")
for р in s.execute("SELECT domain FROM recipients WHERE domain IS NOT NULL"
                   " AND domain<>'' LIMIT 8"):
    print("   ", р["domain"])
print("\n=== ИТОГ: сегменты и группы ===")
print("  segment='meyer':",
      s.execute("SELECT COUNT(*) FROM recipients WHERE segment='meyer'").fetchone()[0])
print("  всего получателей:",
      s.execute("SELECT COUNT(*) FROM recipients").fetchone()[0])
