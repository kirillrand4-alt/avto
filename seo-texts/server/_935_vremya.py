# -*- coding: utf-8 -*-
"""Точное время сегодняшнего пересоздания строк партии-935 и кампании с '935'."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['время_created'] = [dict(r) for r in s.execute(
    "select substr(created_at,1,16) t, count(*) n from recipients "
    "where source='партия-935' group by 1 order by 1")]
итог['кампании_935'] = [dict(r) for r in s.execute(
    "select * from campaigns where name like '%935%'")]
итог['аудит_импортов_всего'] = [dict(r) for r in s.execute(
    "select action, substr(created_at,1,16) t, detail_json from audit_log "
    "where action like '%import%' or action like '%recipient%' "
    "order by id desc limit 8")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4500])
