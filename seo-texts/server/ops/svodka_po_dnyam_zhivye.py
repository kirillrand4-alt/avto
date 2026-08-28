# -*- coding: utf-8 -*-
"""Дневная сводка: отправки, отбивки и ответы ЖИВЫХ людей (без автоответов).

Автоответчик пишется отдельным типом reply_auto — в колонку «живые» он не
попадает; печатаем его рядом, чтобы видно было, сколько шума отсеяно.
"""
import sqlite3
from collections import defaultdict
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
дни = defaultdict(lambda: defaultdict(int))
for r in c.execute(
        "SELECT substr(event_ts,1,10) AS д, event_type AS т, COUNT(*) AS n "
        "  FROM events WHERE event_type IN "
        "        ('sent','bounce','complaint','reply','reply_auto') "
        "   AND event_ts >= '2026-07-01' GROUP BY 1,2"):
    дни[r["д"]][r["т"]] = r["n"]
c.close()

print("%-12s %7s %7s %7s   %7s %7s %7s"
      % ("день", "отпр.", "bounce", "BR%", "ЖИВЫЕ", "доля", "авто"))
print("-" * 62)
итог = defaultdict(int)
for д in sorted(дни):
    с = дни[д]
    if not (с["sent"] or с["reply"] or с["bounce"] or с["reply_auto"]):
        continue
    for к in ("sent", "bounce", "reply", "reply_auto", "complaint"):
        итог[к] += с[к]
    br = (100.0 * с["bounce"] / с["sent"]) if с["sent"] else 0.0
    доля = (100.0 * с["reply"] / с["sent"]) if с["sent"] else 0.0
    print("%-12s %7d %7d %6.2f%%   %7d %6.2f%% %7d"
          % (д, с["sent"], с["bounce"], br, с["reply"], доля, с["reply_auto"]))
print("-" * 62)
br = (100.0 * итог["bounce"] / итог["sent"]) if итог["sent"] else 0.0
доля = (100.0 * итог["reply"] / итог["sent"]) if итог["sent"] else 0.0
print("%-12s %7d %7d %6.2f%%   %7d %6.2f%% %7d"
      % ("ИТОГО", итог["sent"], итог["bounce"], br, итог["reply"], доля,
         итог["reply_auto"]))
print("\nжалоб за всё время: %d" % итог["complaint"])
