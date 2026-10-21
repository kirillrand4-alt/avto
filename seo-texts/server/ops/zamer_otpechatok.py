# -*- coding: utf-8 -*-
"""Диагностика: сколько стоит отпечаток таблицы recipients (только чтение)."""
import sqlite3
import time
c = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
for sql in ("SELECT COUNT(*), MAX(updated_at) FROM recipients",
            "SELECT COUNT(*) FROM recipients", "SELECT MAX(id) FROM recipients",
            "SELECT MAX(updated_at) FROM recipients"):
    for i in range(3):
        t = time.perf_counter(); r = c.execute(sql).fetchone()
        dt = (time.perf_counter() - t) * 1000
    print(f"{dt:7.1f} мс  {sql}  -> {r if 'updated' not in sql else '(есть)' if r[-1] else '(пусто)'}")
print([x[1] for x in c.execute("PRAGMA table_info(recipients)")])
print("=== ГОТОВО ===")
