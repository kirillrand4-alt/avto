# -*- coding: utf-8 -*-
"""Как менялась очередь и сколько за то же время обойдено — по журналу сторожа."""
import io
import json
import os
import sys
import time

D = r'C:\sender\server'
KESH = r'C:\seostat\drop\pagecache'
записи = []
p = r'C:\sender\storozh.jsonl'
if os.path.exists(p):
    for s in io.open(p, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(s)
        except Exception:
            continue
        if 'очередь' in d:
            записи.append(d)
записи = записи[-14:]

# обходы по часам: сколько файлов кэша записано в каждый из последних 8 часов
сейчас = time.time()
по_часам = [0] * 8
for имя in os.listdir(KESH):
    if not имя.endswith('.json.gz'):
        continue
    ч = int((сейчас - os.path.getmtime(os.path.join(KESH, имя))) // 3600)
    if 0 <= ч < 8:
        по_часам[ч] += 1

строки = []
пред = None
for d in записи:
    дельта = (d['очередь'] - пред) if пред is not None else None
    строки.append({'время': d['ts'][11:16], 'очередь': d['очередь'],
                   'изменение': дельта,
                   'поднимал': (d['подняли'] if d['подняли'] != 'ничего не требовалось'
                                else '')})
    пред = d['очередь']
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps({'журнал_сторожа': строки,
                  'обходов_по_часам_назад': по_часам,
                  'порог_долива': 'сторож и демон доливают переобход только когда '
                                  'в очереди меньше 150 строк'},
                 ensure_ascii=False, indent=1))
