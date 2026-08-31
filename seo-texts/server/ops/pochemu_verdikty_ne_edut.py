# -*- coding: utf-8 -*-
"""Работник проверил, а вердиктов в базе нет: где затык."""
import io
import os
import re
import sqlite3
import time

ЛОГИ = [r"C:\sender\_ops\panel_out.log", r"C:\sender\panel_out.log",
        r"C:\sender\_ops\panel.err.log"]
print("=== СЛЕДЫ probe_sync В ЛОГАХ ПАНЕЛИ ===")
for п in ЛОГИ:
    if not os.path.exists(п):
        continue
    размер = os.path.getsize(п)
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    свои = [x for x in с[-4000:]
            if re.search(r"(?i)probe_sync|probesync|забрать|вердикт", x)]
    print("\n-- %s (%d Б, строк в хвосте %d, своих %d)"
          % (os.path.basename(п), размер, len(с[-4000:]), len(свои)))
    for x in свои[-12:]:
        print("   %s" % x[:160])

print("\n=== ПОСЛЕДНИЕ ЗАПИСИ addr_probe ПО ИСТОЧНИКАМ ===")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
for r in c.execute("SELECT COALESCE(source,'') ист, COUNT(*) n, MAX(ts) послед"
                   "  FROM addr_probe GROUP BY ист ORDER BY n DESC LIMIT 8"):
    print("   %-14s %7d  последняя %s" % (r[0] or "—", r[1], r[2]))
за15 = c.execute("SELECT COUNT(*) FROM addr_probe"
                 " WHERE ts >= datetime('now','-15 minutes')").fetchone()[0]
за60 = c.execute("SELECT COUNT(*) FROM addr_probe"
                 " WHERE ts >= datetime('now','-60 minutes')").fetchone()[0]
print("   записей за 15 минут: %d, за час: %d" % (за15, за60))
c.close()

print("\n=== СЕЙЧАС НА СЕРВЕРЕ ===")
print("   время: %s" % time.strftime("%d.%m %H:%M:%S"))
print("   UTC:   %s" % time.strftime("%d.%m %H:%M:%S", time.gmtime()))

print("\n=== ИТОГ ===")
print("если записей за 15 минут ноль, а работник отвечал «проверено 61» —")
print("значит вердикты лежат на дропе, а импорт панели их не забрал.")
