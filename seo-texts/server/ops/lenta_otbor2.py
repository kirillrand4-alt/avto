# -*- coding: utf-8 -*-
"""Отбор ленты лидов: только питон панели. Сводка в конце."""
import io
import os
import re
import sqlite3
from collections import Counter

ФАЙЛЫ = [r"C:\sender\sender\api\app.py", r"C:\sender\sender\store.py",
         r"C:\sender\sender\leads.py", r"C:\sender\sender\reply_desk.py"]

куски = []
for п in ФАЙЛЫ:
    if not os.path.exists(п):
        continue
    т = io.open(п, encoding="utf-8", errors="replace").read()
    for м in re.finditer(r"FROM\s+leads[\s\S]{0,300}", т, re.I):
        кусок = " ".join(м.group(0).split())[:260]
        куски.append("%s:%d| %s" % (os.path.basename(п),
                                    т[:м.start()].count("\n") + 1, кусок))
    for м in re.finditer(r"(not_interested|СТАТУСЫ|STATUSES|reply_kind\s*==)",
                         т):
        н = т.rfind("\n", 0, м.start()) + 1
        к = т.find("\n", м.end())
        куски.append("%s:%d| %s" % (os.path.basename(п),
                                    т[:м.start()].count("\n") + 1,
                                    т[н:к].strip()[:200]))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
статусы = Counter()
пары = Counter()
for с, в in c.execute("SELECT status, reply_kind FROM leads"):
    статусы[с or "(пусто)"] += 1
    пары[(с or "?", в or "?")] += 1
c.close()

print("=" * 74)
print("=== СВОДКА: ЛЕНТА ЛИДОВ ===")
print("статусы лидов:")
for к, в in статусы.most_common():
    print("   %-18s %5d" % (к, в))
print("")
print("пары статус/вид ответа (первые 12):")
for (с, в), н in пары.most_common(12):
    print("   %-18s %-14s %5d" % (с, в, н))
print("")
print("места в коде:")
for с in dict.fromkeys(куски):
    print("   " + с[:230])
