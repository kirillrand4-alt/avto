# -*- coding: utf-8 -*-
"""Только чтение: где лежат почты с сайта и что считается паспортом."""
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

for т in ("emails", "email_sources", "site_facts", "qc_site", "email_class"):
    try:
        кол = [r["name"] for r in e.execute("PRAGMA table_info(%s)" % т)]
        n = e.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("=== %s (%d строк) ===" % (т, n))
        print("  %s" % ", ".join(кол))
        for р in e.execute("SELECT * FROM %s LIMIT 2" % т):
            print("    " + " | ".join("%s=%s" % (k, str(р[k])[:30]) for k in кол)[:190])
    except Exception as ex:
        print("=== %s: %s" % (т, str(ex)[:70]))
    print()

print("=== ИСТОЧНИКИ ПОЧТ ===")
try:
    for р in e.execute("SELECT source, COUNT(*) n FROM emails GROUP BY source"
                       " ORDER BY n DESC LIMIT 12"):
        print("  %-30s %d" % (str(р["source"])[:30], р["n"]))
except Exception as ex:
    print("  %s" % str(ex)[:90])
try:
    for р in e.execute("SELECT istochnik, COUNT(*) n FROM email_sources"
                       " GROUP BY istochnik ORDER BY n DESC LIMIT 12"):
        print("  email_sources.istochnik %-24s %d" % (str(р["istochnik"])[:24], р["n"]))
except Exception as ex:
    print("  email_sources: %s" % str(ex)[:90])

print("\n=== ЧТО ЗНАЧИТ «ПАСПОРТ» В companies ===")
кол = [r["name"] for r in e.execute("PRAGMA table_info(companies)")]
print("  поля про сайт/проверку: %s"
      % ", ".join(k for k in кол if any(s in k for s in
                                        ("site", "verif", "qc", "dokaz", "priznak"))))
for р in e.execute("SELECT verified, COUNT(*) n FROM companies GROUP BY verified"
                   " ORDER BY n DESC LIMIT 8"):
    print("  verified=%-14s %d" % (str(р["verified"]), р["n"]))
