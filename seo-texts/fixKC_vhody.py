# -*- coding: utf-8 -*-
r"""fixKC (21.10): есть ли где-то след входов менеджеров панели КЦ – колонки users, журналы uvicorn/Caddy. Только чтение;
IP и пути печатаются только агрегатно (без cookie/токенов).

    python3 zapusk_na_servere.py fixKC_vhody.py
"""
import collections
import glob
import os
import re
import sqlite3
import time

s = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
kol = [r[1] for r in s.execute('PRAGMA table_info(users)')]
print('колонки users:', kol)
for c in kol:
    if re.search(r'(?i)login|seen|vhod|last', c):
        print('  ', c, s.execute('SELECT username, %s FROM users' % c).fetchall())
kand = []
for pat in (r'C:\seostat\*.log', r'C:\seostat\logs\*', r'C:\seostat\log\*', r'C:\caddy*.log', r'C:\Caddy\*.log',
            r'C:\ProgramData\caddy\**\*.log', r'C:\seostat\data\*.log', r'C:\Windows\System32\config\systemprofile\AppData\Roaming\Caddy\**\*'):
    kand += [p for p in glob.glob(pat, recursive=True) if os.path.isfile(p)]
print('\nфайлы журналов:', [(p, round(os.path.getsize(p) / 2**20, 1), time.strftime('%d.%m %H:%M', time.localtime(os.path.getmtime(p))))
                            for p in kand][:20])
for p in kand:
    try:
        t = open(p, encoding='utf-8', errors='replace').read()[-5_000_000:]
    except OSError:
        continue
    vh = re.findall(r'(\d+\.\d+\.\d+\.\d+)\S*\s+-\s+"POST /obzvon/centro/login[^"]*"\s+(\d{3})', t)
    if vh:
        print('\n%s: POST /obzvon/centro/login: %d, по кодам %s; по IP (успешные 303): %s' % (
            p, len(vh), dict(collections.Counter(k for _, k in vh)),
            dict(collections.Counter(ip for ip, k in vh if k == '303').most_common(8))))
