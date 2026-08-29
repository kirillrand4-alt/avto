# -*- coding: utf-8 -*-
import sqlite3
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True,
                    timeout=60)
o.row_factory = sqlite3.Row
print("obzvon: %s" % ", ".join(r["name"] for r in
                               o.execute("PRAGMA table_info(obzvon)")))
r = o.execute("SELECT * FROM obzvon LIMIT 1").fetchone()
print("\nпример строки:")
for k in r.keys():
    з = str(r[k] or "")
    print("   %-18s %s" % (k, з[:70]))
o.close()
