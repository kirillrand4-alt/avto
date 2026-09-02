# -*- coding: utf-8 -*-
"""Только чтение: таблица шагов последовательности и код enqueue_message."""
import inspect
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
есть = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                " AND name LIKE '%sequence%'")]
print("таблицы: %s" % есть)
for т in есть:
    кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % т)]
    print("  %s: %s" % (т, ", ".join(кол)))
    for р in c.execute("SELECT * FROM %s LIMIT 14" % т):
        print("    " + " | ".join("%s=%s" % (k, str(р[k])[:26]) for k in кол))

print("\n=== внешние ключи messages ===")
for р in c.execute("PRAGMA foreign_key_list(messages)"):
    print("  " + str(dict(р)))
print("  foreign_keys ON: %s" % c.execute("PRAGMA foreign_keys").fetchone()[0])

print("\n=== enqueue_message ===")
print(inspect.getsource(Store.enqueue_message)[:1800])
