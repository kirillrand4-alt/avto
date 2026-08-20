# -*- coding: utf-8 -*-
r"""Скорость цикла фактов: сколько паспортов за час, три и двенадцать часов."""
import json
import sqlite3
import time

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
теперь = time.time()
d = {'колонки': [x[1] for x in c.execute('PRAGMA table_info(site_facts)')]}
for ч in (1, 3, 12):
    п = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(теперь - ч * 3600))
    d['за_%02dч_паспортов' % ч] = c.execute(
        "select count(*) from site_facts where ts>? and coalesce(facts_json,'')<>''",
        (п,)).fetchone()[0]
    d['за_%02dч_записей' % ч] = c.execute(
        'select count(*) from site_facts where ts>?', (п,)).fetchone()[0]
d['последние'] = [{'инн': str(r[0]), 'когда': r[1][11:19], 'note': (r[2] or '')[:60]}
                  for r in c.execute("select inn, ts, note from site_facts "
                                     'order by ts desc limit 5')]
d['без_фактов_всего'] = c.execute(
    "select count(*) from site_facts where coalesce(facts_json,'')=''").fetchone()[0]
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
