# -*- coding: utf-8 -*-
r"""Где в панели живёт фильтр КЦ/Meyer на очереди подтверждения.

Смотрим сервер, а не репозиторий: копии в репозитории отстают, а спрашивают
про то, что видно в живой панели.
"""
import json
import os
import re

d = {}
ФАЙЛЫ = [r'C:\sender\sender\api\app.py', r'C:\sender\sender\store.py',
         r'C:\sender\sender\confirm.py', r'C:\sender\sender\leaddesk.py']
for п in ФАЙЛЫ:
    if not os.path.exists(п):
        d.setdefault('нет файла', []).append(п)
        continue
    with open(п, encoding='utf-8', errors='replace') as f:
        строки = f.readlines()
    имя = os.path.basename(п)
    d.setdefault('размер', {})[имя] = len(строки)
    попал = []
    for i, s in enumerate(строки):
        if re.search(r'napravlenie|napravl|meyer|Meyer|MEYER', s):
            попал.append('%d: %s' % (i + 1, s.strip()[:130]))
    if попал:
        d.setdefault('направление', {})[имя] = попал[:24]
    марш = [('%d: %s' % (i + 1, s.strip()[:110]))
            for i, s in enumerate(строки)
            if re.search(r'@(app|site|router)\.(get|post)\(.*(queue|confirm|ochered)', s)]
    if марш:
        d.setdefault('маршруты', {})[имя] = марш[:20]

# фронт: исходники, восстановленные из sourcemap
корни = [r'C:\sender\_tmp\web-pravki', r'C:\sender\_tmp\web-src-iz-mapy']
for корень in корни:
    if not os.path.isdir(корень):
        continue
    найдено = []
    for путь, _к, файлы in os.walk(корень):
        for ф in файлы:
            if not ф.endswith(('.tsx', '.ts')):
                continue
            п = os.path.join(путь, ф)
            try:
                with open(п, encoding='utf-8', errors='replace') as fh:
                    т = fh.read()
            except OSError:
                continue
            if 'Meyer' in т:
                строки = т.splitlines()
                найдено.append({
                    'файл': п.replace(корень, '')[:60],
                    'строки': ['%d: %s' % (i + 1, s.strip()[:120])
                               for i, s in enumerate(строки)
                               if 'Meyer' in s or 'napravlenie' in s][:14]})
    d.setdefault('фронт', {})[корень] = найдено[:6]
print(json.dumps(d, ensure_ascii=False, indent=1)[:5600])
