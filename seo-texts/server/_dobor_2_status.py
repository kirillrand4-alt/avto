# -*- coding: utf-8 -*-
"""Статус добора: хвост лога, счётчики журнала, что уже легло в базу."""
import json
import os
import sqlite3
import time

LOG = r'C:\sender\_tmp\kesh-dobor.out'
ZH = r'C:\sender\_tmp\kesh-dobor.jsonl'
RO = 'file:C:/sender/enrich.db?mode=ro'

if os.path.exists(LOG):
    t = open(LOG, encoding='utf-8', errors='replace').read()
    print('--- лог (хвост) ---')
    print(t[-2200:])
else:
    print('лога нет')

n = p = tl = ob = prop = 0
if os.path.exists(ZH):
    with open(ZH, encoding='utf-8') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            n += 1
            if d.get('пропуск'):
                prop += 1
                continue
            p += d.get('p', 0)
            tl += d.get('t', 0)
            ob += d.get('obsh', 0)
    print('журнал: строк %d (пропусков %d), почт %d, телефонов %d, общих %d'
          % (n, prop, p, tl, ob))

c = sqlite3.connect(RO, uri=True, timeout=60)
print('в базе с меткой кэш-добор:')
print('  emails (pometka):', c.execute(
    "select count(*) from emails where coalesce(pometka,'') like '%кэш-добор%'").fetchone()[0])
print('  emails (source):', c.execute(
    "select count(*) from emails where source='кэш-добор'").fetchone()[0])
print('  emails source=own-site с нашей пометкой:', c.execute(
    "select count(*) from emails where source='own-site' "
    "and coalesce(pometka,'') like '%кэш-добор%'").fetchone()[0])
print('  phone_contacts:', c.execute(
    "select count(*) from phone_contacts where source like 'кэш-добор%'").fetchone()[0])
print('  из них помечены общими:', c.execute(
    "select count(*) from phone_contacts where source like 'кэш-добор; общий%'").fetchone()[0])
print('  компаний затронуто (почты):', c.execute(
    "select count(distinct inn) from emails where coalesce(pometka,'') like '%кэш-добор%'").fetchone()[0])
print('  компаний затронуто (телефоны):', c.execute(
    "select count(distinct inn) from phone_contacts where source like 'кэш-добор%'").fetchone()[0])
print('  best_email непустых у затронутых:', c.execute(
    "select count(*) from companies where coalesce(best_email,'')<>'' and inn in "
    "(select distinct inn from emails where coalesce(pometka,'') like '%кэш-добор%')").fetchone()[0])
i = r'C:\sender\_tmp\kesh-dobor-itog.json'
print('итоговый файл:', 'есть' if os.path.exists(i) else 'ещё нет')
if os.path.exists(i):
    print(json.dumps(json.load(open(i, encoding='utf-8')), ensure_ascii=False)[:1500])
c.close()
