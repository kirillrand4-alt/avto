# -*- coding: utf-8 -*-
"""Как в панель попадают получатели: следы в аудите и в коде панели."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['действия_загрузки'] = [dict(r) for r in s.execute(
    "select action, count(*) skolko, max(created_at) posledniy from audit_log "
    "where action like '%import%' or action like '%upload%' or action like '%recipient%' "
    "or action like '%base%' group by 1 order by skolko desc limit 10")]
итог['последние_партии'] = [dict(r) for r in s.execute(
    "select coalesce(source,'') partiya, count(*) skolko, min(created_at) s, "
    'max(created_at) po from recipients group by 1 order by po desc limit 6')]
s.close()
# ищем в коде панели, чем грузят
найдено = []
for корень in (r'C:\sender\sender', r'C:\sender\enrich_panel'):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            p = os.path.join(d, f)
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            if re.search(r'INSERT INTO recipients|insert\s+into\s+recipients', t, re.I):
                строки = [i + 1 for i, l in enumerate(t.splitlines())
                          if re.search(r'insert\s+into\s+recipients', l, re.I)]
                найдено.append({'файл': p, 'строки': строки[:5]})
итог['куда_пишутся_получатели'] = найдено
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
