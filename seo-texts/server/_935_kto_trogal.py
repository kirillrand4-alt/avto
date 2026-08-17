# -*- coding: utf-8 -*-
"""Кто сегодня трогал партию-935: у 756 строк created_at стал 17.08 при тех же 757.

Похоже на повторный импорт того же CSV (REPLACE пересоздаёт строку). Смотрим
audit_log и events за сегодня.
"""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
for t in ('audit_log', 'events'):
    кол = [r[1] for r in s.execute('pragma table_info(%s)' % t)]
    итог[t + '_колонки'] = кол
    ts = next((k for k in ('ts', 'created_at', 'time', 'timestamp') if k in кол), кол[0])
    итог[t + '_сегодня'] = [dict(r) for r in s.execute(
        "select * from %s where %s like '2026-08-17%%' order by %s desc limit 12"
        % (t, ts, ts))]
итог['campaigns_935'] = [dict(r) for r in s.execute(
    "select * from campaigns where name like '%935%'")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:5500])
