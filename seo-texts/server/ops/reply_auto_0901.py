# -*- coding: utf-8 -*-
"""Только чтение: когда появился reply_auto и что панель считает ответом."""
import glob
import io
import os
import re
import sqlite3
import sys
from datetime import datetime

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== reply И reply_auto ПО ДНЯМ ===")
print("  %-12s %8s %12s" % ("день", "reply", "reply_auto"))
д = {}
for р in s.execute("SELECT substr(created_at,1,10) d, event_type t, COUNT(*) n"
                   " FROM events WHERE event_type IN ('reply','reply_auto')"
                   " GROUP BY d, t ORDER BY d"):
    д.setdefault(р["d"], {})[р["t"]] = р["n"]
for k in sorted(д):
    print("  %-12s %8d %12d" % (k, д[k].get("reply", 0), д[k].get("reply_auto", 0)))

п = s.execute("SELECT MIN(created_at) m FROM events WHERE event_type='reply_auto'"
              ).fetchone()["m"]
print("\n  ПЕРВОЕ событие reply_auto: %s" % п)

print("\n=== КОНСТАНТЫ ТИПОВ СОБЫТИЙ ===")
sys.path.insert(0, r"C:\sender")
for мод in ("sender.analytics", "sender.imap_watcher"):
    try:
        m = __import__(мод, fromlist=["*"])
        for имя in dir(m):
            if "REPLY" in имя or "OTVET" in имя:
                print("  %s.%s = %r" % (мод, имя, getattr(m, имя)))
    except Exception as ex:
        print("  %s: %s" % (мод, str(ex)[:70]))

print("\n=== ГДЕ РЕШАЕТСЯ, ЧТО ОТВЕТ АВТОМАТИЧЕСКИЙ ===")
for ф in glob.glob(r"C:\sender\sender\*.py"):
    try:
        стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    for i, x in enumerate(стр):
        if "reply_auto" in x:
            print("  --- %s:%d ---" % (os.path.basename(ф), i + 1))
            for j in range(max(0, i - 12), min(i + 6, len(стр))):
                print("     %4d  %s" % (j + 1, стр[j][:104]))
            print()
            break

print("=== ИТОГ: БЭКАПЫ ФАЙЛА, ГДЕ ЭТО ВВЕЛИ ===")
for п2 in sorted(glob.glob(r"C:\sender\sender\imap_watcher.py.bak-*")):
    т = datetime.fromtimestamp(os.path.getmtime(п2))
    print("  %s  %s" % (т.strftime("%m-%d %H:%M"), os.path.basename(п2)))
