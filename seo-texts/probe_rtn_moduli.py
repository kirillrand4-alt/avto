# -*- coding: utf-8 -*-
"""Список управлений берём из модуля 1-й сессии, а не переоткрываем.

ПОВОД. Сайт Ростехнадзора список территориальных органов в разметке не отдаёт: семь разных
разделов дали НОЛЬ поддоменов вида `*.gosnadzor.ru`, включая карту сайта. Продолжать угадывать
пути значит тратить прогоны на то, что у соседей уже лежит готовым: подкоманда `папки` в
`rtn_znaniya.py` перебирает двадцать управлений, и этот перечень зашит прямо в модуле.
Печатаю его и число файлов в потоке — тогда «34 непокрытых» 2-й сессии либо подтвердится,
либо окажется про другое.
"""
import json
import os
import re

o = {}
for p in (r'C:\seostat\app\ops\rtn_znaniya.py', r'C:\sender\ops\rtn_znaniya.py',
          r'C:\sender\rtn_znaniya.py', r'C:\seostat\ops\rtn_znaniya.py'):
    if os.path.exists(p):
        o['модуль'] = p
        src = open(p, encoding='utf-8', errors='replace').read()
        pd = sorted(set(re.findall(r'([a-z0-9\-]{2,})\.gosnadzor\.ru', src)))
        o['управлений_в_модуле'] = len(pd)
        o['управления'] = pd
        break
else:
    o['модуль'] = 'НЕ НАЙДЕН по четырём путям'
for p in (r'C:\seostat\drop\rtn_files.jsonl', r'C:\seostat\drop\rtn_rows.jsonl'):
    if os.path.exists(p):
        n = sum(1 for _ in open(p, encoding='utf-8', errors='replace'))
        o[os.path.basename(p)] = n
        if p.endswith('files.jsonl'):
            host = {}
            for ln in open(p, encoding='utf-8', errors='replace'):
                m = re.search(r'https?://([a-z0-9\-]+)\.gosnadzor\.ru', ln)
                if m:
                    host[m.group(1)] = host.get(m.group(1), 0) + 1
            o['файлов_по_управлениям'] = sorted(host.items(), key=lambda x: -x[1])
print(json.dumps(o, ensure_ascii=False))
