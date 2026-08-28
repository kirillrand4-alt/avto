# -*- coding: utf-8 -*-
"""Какой чистильщик съедает подпись главного механика на публичной странице."""
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender import lid_ssylka as LS                                # noqa: E402

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
d = json.loads(c.execute("SELECT detail_json FROM events WHERE id=305587"
                         ).fetchone()[0] or "{}")
c.close()
т = str(d.get("snippet") or "")
шаги = [("исходник", т)]
for имя, f in (("bez_citaty", LS.bez_citaty),
               ("bez_nashey_podpisi", LS.bez_nashey_podpisi),
               ("bez_adresov", LS.bez_adresov)):
    т = f(т)
    шаги.append((имя, т))
for имя, з in шаги:
    print("### %s — %d знаков" % (имя, len(з)))
    for стр in з.split("\n"):
        print("    %s" % стр[:150])
    print()
