# -*- coding: utf-8 -*-
"""Кто отдаёт панели людей карточки. Найти подачу, а не догадываться о ней.

Скрытие людей панель не читает: единственное упоминание `kind='person'` стоит в чужом
скрипте, который это скрытие ПИШЕТ. Мой прибор сначала объявил «читает: true» — он
посчитал чужую запись за чтение. Второй раз за час собственный счётчик принял эхо за
чужой голос, и оба раза в утвердительную сторону.

Значит надо найти саму подачу: службу, которая отдаёт карточку предприятия с людьми.
Ищу по двум признакам сразу — файл трогает базу панели И объявляет обработчики запросов
(маршруты, `op ==`, роуты). Печатает имена обработчиков: по ним видно, какой отдаёт людей.

Ничего не пишет.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender', r'C:\seostat')
MOYO = re.compile(r'[\\/](?:_ops|_bak[^\\/]*)[\\/]|[\\/][123]s_|_[123]s\.py$', re.I)
BAZA = re.compile(r'centrifugal\.db|centro_sales\.db', re.I)
SLUZHBA = re.compile(r'@app\.(?:route|get|post)|app\.route|FastAPI\(|Flask\(|'
                     r'BaseHTTPRequestHandler|aiohttp|def\s+do_(?:GET|POST)|'
                     r"args\.get\('op'\)|args\.get\(\"op\"\)", re.I)
OBRABOTCHIK = re.compile(r"op'\)\s*==\s*'([a-z_0-9]+)'|op\"\)\s*==\s*\"([a-z_0-9]+)\"|"
                         r"@app\.(?:route|get|post)\(\s*['\"]([^'\"]+)['\"]", re.I)

sch = collections.Counter()
sluzhby = collections.defaultdict(list)
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(put, f)
            if MOYO.search(p) or p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 8 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if not (BAZA.search(t) and SLUZHBA.search(t)):
                continue
            sch['служб, трогающих базу панели'] += 1
            imena = []
            for m in OBRABOTCHIK.finditer(t):
                imya = m.group(1) or m.group(2) or m.group(3)
                if imya and imya not in imena:
                    imena.append(imya)
            # Обработчики, в имени которых человек или контакт.
            pro_lyudey = [i for i in imena
                          if re.search(r'lpr|person|people|lyud|contact|kontakt|card|'
                                       r'kartochk|company|predpr', i, re.I)]
            sluzhby[p] = (len(imena), pro_lyudey[:12], imena[:6])

for p, (n, pro, vse) in sorted(sluzhby.items(), key=lambda x: -x[1][0])[:12]:
    print('\n--- %s   обработчиков %d' % (p[-64:], n))
    if pro:
        print('    про людей/карточку: %s' % ', '.join(pro))
    print('    первые: %s' % ', '.join(vse))

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'служб найдено': len(sluzhby)}, ensure_ascii=False))
