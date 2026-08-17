# -*- coding: utf-8 -*-
"""Не встал ли разбор фактов, пока модель молчит: карточки по часам."""
import json
import sqlite3
import sys
import time

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
по_часам = {}
for (ts,) in c.execute("select ts from site_facts where coalesce(facts_json,'')<>'' "
                       "and ts > ?", (time.strftime('%Y-%m-%dT00:00:00'),)):
    по_часам[str(ts)[11:13]] = по_часам.get(str(ts)[11:13], 0) + 1
всего2 = c.execute("select count(*) from site_facts where coalesce(format,0)>=2").fetchone()[0]
ждут = c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>'' "
                 "and coalesce(format,0)<2").fetchone()[0]
c.close()
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({'карточек_по_часам_сегодня': dict(sorted(по_часам.items())),
                  'формат_2_всего': всего2, 'ждут_переразбора': ждут,
                  'сейчас': time.strftime('%H:%M')}, ensure_ascii=False, indent=1))
