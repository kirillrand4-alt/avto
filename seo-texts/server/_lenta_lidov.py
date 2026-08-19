# -*- coding: utf-8 -*-
"""Устройство ленты лидов: таблицы, статусы, ручки API, файлы веб-морды."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
итог['leads_колонки'] = [r[1] for r in s.execute('pragma table_info(leads)')]
итог['lead_events_колонки'] = [r[1] for r in s.execute('pragma table_info(lead_events)')]
итог['по_статусам'] = [list(r) for r in s.execute(
    "select coalesce(status,'(пусто)'), count(*) from leads group by 1 order by 2 desc")]
итог['всего_лидов'] = s.execute('select count(*) from leads').fetchone()[0]
s.close()
# ручки API
путь_app = ''
for d, _, fs in os.walk(r'C:\sender\sender'):
    if 'app.py' in fs:
        путь_app = os.path.join(d, 'app.py')
        break
итог['app_py'] = путь_app
t = io.open(путь_app, encoding='utf-8', errors='replace').read() if путь_app else ''
итог['ручки_лидов'] = [l.strip()[:110] for l in t.splitlines()
                       if re.search(r'lead', l, re.I) and
                       re.search(r'@app\.(get|post|put|patch|delete)|def ', l)][:20]
# где живёт веб-морда
корни = []
for к in (r'C:\sender\web', r'C:\sender\web\dist'):
    if os.path.exists(к):
        файлы = []
        for d, _, fs in os.walk(к):
            for f in fs:
                p = os.path.join(d, f)
                файлы.append((os.path.relpath(p, к), os.path.getsize(p)))
        файлы.sort(key=lambda x: -x[1])
        корни.append({'путь': к, 'файлов': len(файлы), 'крупные': файлы[:8]})
итог['веб'] = корни
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4000])
