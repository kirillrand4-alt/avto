# -*- coding: utf-8 -*-
"""Что такое партия 935 и сколько из неё ушло оператору на проверку."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['таблицы'] = [r[0] for r in s.execute(
    "select name from sqlite_master where type='table' order by name")]
for т in ('confirm_reviews', 'ai_letter_log', 'send_log', 'recipients', 'campaigns'):
    try:
        итог[т + '_колонки'] = [r[1] for r in s.execute('pragma table_info(%s)' % т)]
        итог[т + '_строк'] = s.execute('select count(*) from %s' % т).fetchone()[0]
    except Exception as e:  # noqa: BLE001
        итог[т + '_ошибка'] = str(e)[:60]
try:
    итог['очередь_по_статусам'] = [dict(r) for r in s.execute(
        "select campaign_id, status, count(*) skolko from confirm_reviews "
        'group by campaign_id, status order by campaign_id')]
except Exception as e:  # noqa: BLE001
    итог['очередь_ошибка'] = str(e)[:80]
try:
    итог['кампании'] = [dict(r) for r in s.execute(
        'select id, name, status from campaigns order by id')]
except Exception as e:  # noqa: BLE001
    итог['кампании_ошибка'] = str(e)[:80]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
