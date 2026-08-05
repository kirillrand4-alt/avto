# -*- coding: utf-8 -*-
"""Пустит ли токен user3 на card-роут. Его я ещё не пробовала именно на /centroN/card.

Раньше user3 отвергался на /obzvon/centro — но это оболочка-форма, она такая всегда.
Настоящий вход проверяется на data-роуте /obzvon/centroN/card?skip=0 (там 401 без кред).
Файл user3 назван «P25, панель покупателей 2025» — это ровно centro. Проверяю его на
card-роутах centro и centro1..2. Пароль не печатаю; печатаю код и есть ли на странице
живая карточка (ct-person).
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

PANEL = 'http://127.0.0.1:8012'
PUTI = ['/obzvon/centro/card?skip=0', '/obzvon/centro1/card?skip=0',
        '/obzvon/centro2/card?skip=0', '/obzvon/centro/list?page=1',
        '/obzvon/centro1/list?page=1']


def user3():
    p = r'C:\sender\_ops\p25_user3_token.txt'
    lg = pw = ''
    if os.path.exists(p):
        for s in io.open(p, encoding='utf-8', errors='replace').read().split('\n'):
            m = re.match(r'\s*(?:логин|login)\s*[:=]\s*(\S.*)$', s, re.I)
            if m:
                lg = m.group(1).strip()
            m = re.match(r'\s*(?:пароль|password)\s*[:=]\s*(\S.*)$', s, re.I)
            if m:
                pw = m.group(1).strip()
    return lg, pw


lg, pw = user3()
avt = 'Basic ' + base64.b64encode(('%s:%s' % (lg, pw)).encode()).decode()
print('логин из файла: %s (пароль длиной %d)' % (lg or '—', len(pw)))
vosh = ''
for put in PUTI:
    rq = urllib.request.Request(PANEL + put)
    rq.add_header('Authorization', avt)
    rq.add_header('User-Agent', 'progulka-3s')
    try:
        with urllib.request.urlopen(rq, timeout=40) as o:
            kod, telo = o.status, o.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        kod, telo = e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        kod, telo = 0, '__ОШИБКА__ %s' % type(e).__name__
    karta = 'ct-person' in telo or 'ct-card' in telo or 'Люди с должностями' in telo
    forma = bool(re.search(r'name="?password', telo, re.I))
    print('  %-30s код %-4s длина %-6d карточка %s форма %s'
          % (put, kod, len(telo), 'ДА' if karta else '-', 'да' if forma else '-'))
    if karta and not forma and not vosh:
        vosh = put
print('ИТОГ ' + json.dumps({'вошли user3': bool(vosh), 'где': vosh}, ensure_ascii=False))
