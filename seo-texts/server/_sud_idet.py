# -*- coding: utf-8 -*-
"""Жив ли процесс судьи и счётчики вердиктов — одной строкой."""
import json
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%prigovor_domenov%--sudit%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
жив = any(x.strip().isdigit() for x in (p.stdout or '').splitlines())
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
счёт = dict(c.execute(
    'select verdikt, count(*) from prigovor_domenov group by 1').fetchall())
c.close()
print(json.dumps({'идёт': жив, 'счёт': счёт}, ensure_ascii=False))
