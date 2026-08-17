# -*- coding: utf-8 -*-
"""Откуда прилетел баунс: что записано в базе рассыльщика."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
c.row_factory = sqlite3.Row
таблицы = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table'")]
итог = {'таблицы_про_отказы': [t for t in таблицы
                               if any(k in t.lower() for k in
                                      ('bounce', 'otkaz', 'reply', 'event', 'delivery',
                                       'sent', 'message'))]}
for t in итог['таблицы_про_отказы']:
    try:
        колонки = [r[1] for r in c.execute('pragma table_info(%s)' % t)]
        n = c.execute('select count(*) from %s' % t).fetchone()[0]
        итог[t] = {'строк': n, 'колонки': колонки[:14]}
    except Exception as e:  # noqa: BLE001
        итог[t] = {'ошибка': str(e)[:80]}
print(json.dumps(итог, ensure_ascii=False, indent=1))
c.close()
