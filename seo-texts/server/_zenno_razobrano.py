# -*- coding: utf-8 -*-
"""Что в zenno\\razobrano, кто его читает и есть ли эти данные в pagecache."""
import io
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
R = r'C:\seostat\drop\zenno\razobrano'
KESH = r'C:\seostat\drop\pagecache'
итог = {}
файлы = []
try:
    for e in os.scandir(R):
        if e.is_file():
            st = e.stat()
            файлы.append((e.name, st.st_size, st.st_mtime))
except OSError as ex:
    итог['беда'] = str(ex)
итог['файлов'] = len(файлы)
итог['ГБ'] = round(sum(s for _, s, _ in файлы) / 2**30, 1)
файлы.sort(key=lambda x: -x[1])
итог['самые_тяжёлые'] = [[n, round(s / 2**20, 1),
                          time.strftime('%Y-%m-%d', time.localtime(t))]
                         for n, s, t in файлы[:5]]
if файлы:
    даты = sorted(time.strftime('%Y-%m-%d', time.localtime(t)) for _, _, t in файлы)
    итог['период'] = [даты[0], даты[-1]]
    итог['расширения'] = {}
    for n, _, _ in файлы:
        р = os.path.splitext(n)[1].lower() or '(нет)'
        итог['расширения'][р] = итог['расширения'].get(р, 0) + 1
# кто читает razobrano
кто = []
for корень in (r'C:\sender\server', r'C:\sender\sender', r'C:\seostat\drop'):
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
            if 'razobrano' in t:
                строки = [l.strip()[:100] for l in t.splitlines() if 'razobrano' in l]
                кто.append({'файл': f, 'строки': строки[:4]})
итог['кто_упоминает'] = кто
итог['в_кэше_файлов'] = len([1 for x in os.listdir(KESH) if x.endswith('.json.gz')])
print(json.dumps(итог, ensure_ascii=False))
