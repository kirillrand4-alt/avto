# -*- coding: utf-8 -*-
"""Как устроена проверка адресов работником: таблица addr_probe и её код."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог['колонки'] = [r[1] for r in s.execute('pragma table_info(addr_probe)')]
итог['всего'] = s.execute('select count(*) from addr_probe').fetchone()[0]
кол = итог['колонки']
for поле in ('status', 'state', 'verdict', 'result'):
    if поле in кол:
        итог['по_' + поле] = [dict(r) for r in s.execute(
            'select %s v, count(*) n from addr_probe group by 1 order by n desc limit 8'
            % поле)]
итог['последние'] = [{k: (str(v)[:60] if v is not None else None)
                      for k, v in dict(r).items()}
                     for r in s.execute('select * from addr_probe order by rowid desc limit 3')]
s.close()
# код, который с ней работает
места = []
for корень in (r'C:\sender\sender', r'C:\sender\server'):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            try:
                t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if 'addr_probe' in t:
                строки = [l.strip()[:110] for l in t.splitlines()
                          if 'addr_probe' in l or re.search(r'def .*(probe|proba)', l)]
                места.append({'файл': f, 'строки': строки[:8]})
итог['код'] = места
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4200])
