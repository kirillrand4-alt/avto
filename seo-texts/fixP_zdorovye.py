# -*- coding: utf-8 -*-
r"""fixP: состояние панели Meyer после обрыва агентов – замок, свежие правки кода, ответ панели. Только чтение.

    python3 zapusk_na_servere.py fixP_zdorovye.py
"""
import os
import time
import urllib.request

KOREN = r'C:\centro2'
ZAMOK = os.path.join(KOREN, '_zamok.txt')

if os.path.exists(ZAMOK):
    print('ЗАМОК: %s (возраст %.0f с)' % (open(ZAMOK, encoding='utf-8').read(), time.time() - os.path.getmtime(ZAMOK)))
else:
    print('замка нет')
svezhie = []
for kor, _, fajly in os.walk(os.path.join(KOREN, 'app')):
    for f in fajly:
        p = os.path.join(kor, f)
        vozr = time.time() - os.path.getmtime(p)
        if vozr < 4 * 3600 and not f.endswith('.pyc'):
            svezhie.append((round(vozr / 60), p))
print('файлы кода, изменённые за 4 часа:', sorted(svezhie) or 'нет')
try:
    k = urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=15).status
except Exception as e:  # noqa: BLE001
    k = repr(e)
print('панель /login:', k)
