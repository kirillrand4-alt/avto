# -*- coding: utf-8 -*-
"""Кладёт локальный файл в C:\\sender\\_ops\\ на сервере — правильной формой panel_file_put.

Ловушка, из-за которой заведён этот помощник: у panel_file_put ключ **files** со списком
{"dest","b64"}. Если позвать его с "path"/"content" (как кажется естественным), операция
вернёт `ok: true, errors: []` и НЕ НАПИШЕТ НИЧЕГО — списка файлов нет, писать нечего.
Ошибка тихая: узнаёшь о ней только когда panel_py не находит скрипт.

Запуск: python3 srv_put.py <локальный.py> [ещё файлы...]
"""
import base64, json, os, subprocess, sys

SRV = '/home/user/avto/seo-texts/server'
fajly = []
for p in sys.argv[1:]:
    fajly.append({'dest': 'C:\\sender\\_ops\\' + os.path.basename(p),
                  'b64': base64.b64encode(open(p, 'rb').read()).decode()})
zad = json.dumps({'op': 'panel_file_put', 'files': fajly})
r = subprocess.run([sys.executable, 'run_on_server.py', 'enrich_contacts', zad],
                   cwd=SRV, capture_output=True, text=True, timeout=600)
print(r.stdout[-800:] or r.stderr[-800:])
