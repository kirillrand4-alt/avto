# -*- coding: utf-8 -*-
"""Отрасль и станок у получателей по имени: stanok_u_kogo.py <regex имени>."""
import json
import re
import sqlite3
import sys
рег = re.compile(sys.argv[1], re.I)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for rid, имя, сег, ex in c.execute("SELECT id, company_name, segment, extra_json FROM recipients "
                                    "WHERE extra_json LIKE '%gruppy%'"):
    if not рег.search(str(имя)):
        continue
    д = json.loads(ex or "{}")
    print("%s | %s | сегмент=%s | станок=%s | группы=%s" % (rid, имя, сег, д.get("meyer_gradaciya"),
                                                            д.get("gruppy")))
print("=== ГОТОВО ===")
