# -*- coding: utf-8 -*-
"""Только чтение: как оркестратор выбирает созревшие письма."""
import io
import re
import sqlite3
from datetime import datetime, timezone

стр = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
              errors="replace").read().splitlines()
print("=== ЗАПРОСЫ, ВЫБИРАЮЩИЕ scheduled ===")
for i, x in enumerate(стр):
    if "scheduled_at" in x and re.search(r"<=|<|BETWEEN", x):
        print("  --- store.py:%d ---" % (i + 1))
        for j in range(max(0, i - 10), min(i + 8, len(стр))):
            print("     %4d  %s" % (j + 1, стр[j][:104]))
        print()

print("=== ИТОГ: ПРОВЕРКА СРАВНЕНИЯ НА ЖИВЫХ ДАННЫХ ===")
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
print("  ISO-время как его пишет питон: %s" % now_iso)
print("  datetime('now') в SQLite      : %s"
      % s.execute("SELECT datetime('now') n").fetchone()["n"])
a = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= datetime('now')").fetchone()["n"]
b = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= ?", (now_iso,)).fetchone()["n"]
print("  созрело при сравнении с datetime('now') [пробел]: %d" % a)
print("  созрело при сравнении с ISO-строкой  [буква T]  : %d" % b)
print("  <- вторая цифра верная: формат совпадает с тем, как лежит scheduled_at")
