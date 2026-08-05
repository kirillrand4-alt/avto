# -*- coding: utf-8 -*-
"""Переписывание пути: снаружи /p25, приложению — привычный /obzvon.

Панель на 8014 отдаёт 200 только на `/obzvon/centro/login`: префикс зашит в
самом приложении, а не задан параметром запуска. Поэтому голый проброс дал 404.
Ставлю в маршрут переписывание `^/p25` → `/obzvon` перед проксированием.
"""
import json, sys, time, urllib.request
АДМИН = 'http://127.0.0.1:2019'
ПУТЬ = '/config/apps/http/servers/srv0/routes/2/handle/0/routes/0'

def взять(п):
    return json.loads(urllib.request.urlopen(АДМИН + п, timeout=20).read().decode())

def послать(п, тело, метод='PATCH'):
    з = urllib.request.Request(АДМИН + п, data=json.dumps(тело).encode(),
                               headers={'Content-Type': 'application/json'}, method=метод)
    return urllib.request.urlopen(з, timeout=30).read().decode()

м = взять(ПУТЬ)
пути = []
for с in (м.get('match') or []):
    пути += с.get('path') or []
if not any(п.startswith('/p25') for п in пути):
    print('маршрут 0 — не мой /p25, ничего не трогаю:', json.dumps(м, ensure_ascii=False)[:140])
    raise SystemExit
внутр = м['handle'][0]['routes']
уже = json.dumps(внутр, ensure_ascii=False)
if 'rewrite' in уже:
    print('переписывание уже стоит'); raise SystemExit
внутр.insert(0, {'handle': [{'handler': 'rewrite',
                             'path_regexp': [{'find': '^/p25', 'replace': '/obzvon'}]}]})
послать(ПУТЬ, м, 'PATCH')
time.sleep(2)
проверка = json.dumps(взять(ПУТЬ), ensure_ascii=False)
print('в маршруте есть rewrite:', 'rewrite' in проверка)
print(проверка[:320])
