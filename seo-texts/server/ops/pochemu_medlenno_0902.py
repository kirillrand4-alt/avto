# -*- coding: utf-8 -*-
"""Только чтение: почему панель долго грузит экран подтверждений."""
import datetime as dt
import os
import sqlite3
import time

for п in (r"C:\sender\sender.db", r"C:\sender\sender.db-wal",
          r"C:\sender\sender.db-shm"):
    if os.path.exists(п):
        print("  %-28s %10.1f МБ  изменён %s"
              % (os.path.basename(п), os.path.getsize(п) / 1048576.0,
                 dt.datetime.fromtimestamp(os.path.getmtime(п)).strftime("%H:%M:%S")))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== РАЗМЕРЫ ТАБЛИЦ ===")
for т in ("messages", "confirm_reviews", "events", "recipients", "send_log",
          "suppression", "addr_probe"):
    try:
        n = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("  %-18s %8d строк" % (т, n))
    except Exception as ex:
        print("  %-18s %s" % (т, str(ex)[:50]))

print("\n=== ВЕС panel_json В ОЧЕРЕДИ ПОДТВЕРЖДЕНИЙ ===")
р = c.execute("SELECT COUNT(*) n, SUM(LENGTH(panel_json)) b,"
              " AVG(LENGTH(panel_json)) a FROM confirm_reviews"
              " WHERE status='pending'").fetchone()
print("  ожидают решения: %s, суммарно panel_json %.1f МБ, в среднем %.0f КБ"
      % (р["n"], (р["b"] or 0) / 1048576.0, (р["a"] or 0) / 1024.0))

print("\n=== СКОЛЬКО ЖДЁТ ТИПОВОЙ ЗАПРОС ЭКРАНА ===")
t = time.time()
n = len(c.execute("SELECT * FROM confirm_reviews WHERE status='pending'"
                  " ORDER BY id DESC LIMIT 50").fetchall())
print("  выборка 50 карточек со всеми полями: %.2f с (%d строк)"
      % (time.time() - t, n))
t = time.time()
c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'").fetchone()
print("  подсчёт ожидающих: %.2f с" % (time.time() - t))

print("\n=== ИНДЕКСЫ confirm_reviews ===")
for р2 in c.execute("SELECT name, sql FROM sqlite_master WHERE type='index'"
                    " AND tbl_name='confirm_reviews'"):
    print("  %s" % (str(р2["sql"]) or р2["name"])[:100])
