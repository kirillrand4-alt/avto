# -*- coding: utf-8 -*-
"""Хвост лога судьи + счётчики из таблицы."""
import io
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
п = r'C:\sender\server\prigovor-domenov.log'
if os.path.exists(п):
    т = io.open(п, encoding='utf-8', errors='replace').read()
    итог['лог_хвост'] = т[-900:]
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
try:
    итог['в_таблице'] = dict(c.execute(
        'select verdikt, count(*) from prigovor_domenov group by 1').fetchall())
except Exception as e:  # noqa: BLE001
    итог['в_таблице'] = str(e)
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
