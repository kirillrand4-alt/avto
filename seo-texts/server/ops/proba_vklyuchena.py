# -*- coding: utf-8 -*-
"""Включён ли цикл пробы и что он сделал в последний раз."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
таблицы = [р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print("таблицы с настройками: %s"
      % ", ".join(т for т in таблицы if "set" in т.lower() or "конф" in т))
for т in таблицы:
    кол = [к[1] for к in c.execute("PRAGMA table_info(%s)" % т)]
    if "key" in кол and "value" in кол:
        строки = c.execute("SELECT key, value FROM %s WHERE key LIKE '%%probe%%'"
                           " OR key LIKE '%%auto%%'" % т).fetchall()
        if строки:
            print("\n=== %s ===" % т)
            for р in строки:
                print("  %-34s = %s" % (р["key"], str(р["value"])[:60]))
