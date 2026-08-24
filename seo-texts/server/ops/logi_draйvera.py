# -*- coding: utf-8 -*-
"""Ровно два файла: лог обёртки запуска и лог блока."""
import io
import os
import time

for п in (r"C:\sender\_ops\ochered_vladeltsa-0824-161012.log",
          r"C:\sender\_ops\ochered_vladeltsa-0824-155517.log",
          r"C:\sender\_ops\ochered-blok1-meyer.log"):
    if not os.path.exists(п):
        print("НЕТ ФАЙЛА: %s\n" % п)
        continue
    print("=== %s (%d байт, %.1f мин назад) ==="
          % (os.path.basename(п), os.path.getsize(п),
             (time.time() - os.path.getmtime(п)) / 60.0))
    print(io.open(п, encoding="utf-8", errors="replace").read()[-3000:])
    print()

print("=== ЧТО СЕЙЧАС В ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ ===")
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT status, COUNT(*) n, MIN(created_at) a, MAX(created_at) b "
        "  FROM confirm_reviews GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d   с %s по %s"
          % (р["status"], р["n"], str(р["a"])[:16], str(р["b"])[:16]))
print("\n  из pending — по времени создания:")
for р in c.execute(
        "SELECT substr(created_at,1,13) ч, COUNT(*) n FROM confirm_reviews "
        " WHERE status='pending' GROUP BY ч ORDER BY ч DESC LIMIT 8"):
    print("    %s  %d" % (р["ч"], р["n"]))
print("\n  из них починенных сегодня (спасённые):")
н = c.execute("SELECT COUNT(*) n FROM confirm_reviews "
              " WHERE status='pending' AND substr(created_at,1,10)=date('now')"
              ).fetchone()["n"]
print("    заведено сегодня: %d" % н)
