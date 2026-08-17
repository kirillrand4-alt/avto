# -*- coding: utf-8 -*-
"""Баунсы в sender.db: таблицы events и send_log."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
c.row_factory = sqlite3.Row
итог = {}
for т in ('events', 'send_log'):
    итог[т + '_колонки'] = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
try:
    итог['типы_событий'] = [dict(r) for r in c.execute(
        "select type, count(*) skolko, max(created_at) posledniy from events "
        "group by type order by skolko desc limit 12")]
except Exception as e:  # noqa: BLE001
    итог['типы_ошибка'] = str(e)[:120]
try:
    итог['последние_события'] = [dict(r) for r in c.execute(
        "select * from events order by id desc limit 6")]
except Exception as e:  # noqa: BLE001
    итог['события_ошибка'] = str(e)[:120]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3200])
c.close()
