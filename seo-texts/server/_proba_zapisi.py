# -*- coding: utf-8 -*-
r"""Можно ли вообще писать в enrich.db прямо сейчас: одна короткая транзакция."""
import json
import sqlite3
import time

d = {}
c = sqlite3.connect(r'C:\sender\enrich.db', timeout=15)
c.execute('PRAGMA busy_timeout=15000')
t0 = time.time()
try:
    c.execute('BEGIN IMMEDIATE')
    c.execute("CREATE TABLE IF NOT EXISTS _proba_zapisi(k TEXT, ts TEXT)")
    c.execute('INSERT INTO _proba_zapisi VALUES(?,?)',
              ('проба', time.strftime('%H:%M:%S')))
    c.commit()
    d['запись'] = 'удалась'
except Exception as e:  # noqa: BLE001
    d['запись'] = str(e)[:120]
d['секунд_на_попытку'] = round(time.time() - t0, 2)
try:
    c.execute('DROP TABLE IF EXISTS _proba_zapisi')
    c.commit()
except Exception:  # noqa: BLE001
    pass
d['режим_журнала'] = c.execute('PRAGMA journal_mode').fetchone()[0]
c.close()
import os
for п in (r'C:\sender\enrich.db-wal', r'C:\sender\enrich.db-shm'):
    if os.path.exists(п):
        d[os.path.basename(п)] = os.path.getsize(п)
print(json.dumps(d, ensure_ascii=False, indent=1))
