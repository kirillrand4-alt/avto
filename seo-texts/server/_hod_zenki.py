# -*- coding: utf-8 -*-
r"""Что приносит Зенка: круги моста с числами приёма."""
import json
import os
import time

д = {}
п = r'C:\seostat\drop\zenno\demon.out'
if os.path.exists(п):
    строки = [s.strip() for s in open(п, encoding='utf-8', errors='replace')
              if s.strip()]
    д['круги'] = []
    for s in строки[-6:]:
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            д['круги'].append(s[:150])
            continue
        д['круги'].append({'время': o.get('время'),
                           'приём': o.get('приём') or o.get('priyom'),
                           'доработка': o.get('доработка'),
                           'очередь': (o.get('очередь') or {}).get('дописано')})
    д['лог_обновлён_сек'] = int(time.time() - os.path.getmtime(п))
# сколько файлов прибыло за 10 минут
g = r'C:\seostat\drop\zenno\gotovo'
порог = time.time() - 600
n = св = 0
with os.scandir(g) as it:
    for e in it:
        n += 1
        try:
            if e.stat().st_mtime >= порог:
                св += 1
        except OSError:
            pass
д['gotovo'] = {'файлов': n, 'за_10мин': св}
k = r'C:\seostat\drop\pagecache'
порог = time.time() - 3600
кn = кс = 0
with os.scandir(k) as it:
    for e in it:
        if not e.name.endswith('.json.gz'):
            continue
        кn += 1
        try:
            if e.stat().st_mtime >= порог:
                кс += 1
        except OSError:
            pass
д['кэш'] = {'файлов': кn, 'за_час': кс}
print(json.dumps(д, ensure_ascii=False, indent=1)[:2500])
